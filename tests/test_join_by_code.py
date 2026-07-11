"""
Tests unitaires — S2-08 Join by Code

Couvre :
  - generate_invitation_code (admin)
  - join_by_code (utilisateur)
  - get_user_organizations
  - leave_organization
  - Sécurité : code expiré, déjà membre, code invalide
"""
import pytest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from unittest.mock import patch

from app.services.organization_service import OrganizationService
from app.schemas.organization import (
    CreateOrganizationRequest,
    GenerateInvitationCodeRequest,
    JoinByCodeRequest,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def org_service(db_session):
    return OrganizationService(db_session)


async def _create_org(org_service, slug="bcb", name="BCB") -> str:
    org = await org_service.create(CreateOrganizationRequest(
        name=name, slug=slug, sector="bank"
    ))
    return org.id


# ── Generate Invitation Code ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_generate_invitation_code_success(org_service):
    """Un admin peut générer un code d'invitation pour son org."""
    org_id = await _create_org(org_service)
    result = await org_service.generate_invitation_code(
        org_id, GenerateInvitationCodeRequest(expires_in_days=30)
    )

    assert result.invitation_code is not None
    assert len(result.invitation_code) == 8
    assert result.invitation_code == result.invitation_code.upper()  # uppercase obligatoire
    assert result.invitation_code_active is True
    assert result.invitation_expires_at is not None


@pytest.mark.asyncio
async def test_generate_invitation_code_replaces_old_code(org_service):
    """Générer un nouveau code invalide l'ancien."""
    org_id = await _create_org(org_service)

    first = await org_service.generate_invitation_code(
        org_id, GenerateInvitationCodeRequest(expires_in_days=30)
    )
    second = await org_service.generate_invitation_code(
        org_id, GenerateInvitationCodeRequest(expires_in_days=30)
    )

    # Les codes doivent être différents
    assert first.invitation_code != second.invitation_code


@pytest.mark.asyncio
async def test_generate_code_org_not_found_raises_404(org_service):
    """Organisation inexistante → 404."""
    with pytest.raises(HTTPException) as exc_info:
        await org_service.generate_invitation_code(
            "bad-id", GenerateInvitationCodeRequest()
        )
    assert exc_info.value.status_code == 404


# ── Join by Code ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_join_by_valid_code(org_service):
    """Un utilisateur peut rejoindre une org avec un code valide."""
    org_id = await _create_org(org_service)
    code_result = await org_service.generate_invitation_code(
        org_id, GenerateInvitationCodeRequest(expires_in_days=30)
    )

    result = await org_service.join_by_code(
        code=code_result.invitation_code,
        user_id="user-123",
    )

    assert result.user_id == "user-123"
    assert result.organization_id == org_id
    assert result.status == "active"


@pytest.mark.asyncio
async def test_join_by_code_case_insensitive(org_service):
    """Le code fonctionne en minuscules aussi — normalisé en uppercase."""
    org_id = await _create_org(org_service)
    code_result = await org_service.generate_invitation_code(
        org_id, GenerateInvitationCodeRequest(expires_in_days=30)
    )

    # Envoyer le code en minuscules
    result = await org_service.join_by_code(
        code=code_result.invitation_code.lower(),
        user_id="user-456",
    )
    assert result.status == "active"


@pytest.mark.asyncio
async def test_join_by_expired_code_fails(org_service):
    """Code expiré → 404 (même message que code invalide — pas d'info sur expiration)."""
    org_id = await _create_org(org_service)
    await org_service.generate_invitation_code(
        org_id, GenerateInvitationCodeRequest(expires_in_days=1)
    )

    # Forcer l'expiration en modifiant directement la DB
    from sqlalchemy import select
    from app.models.organization import Organization
    result = await org_service.db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one()
    org.invitation_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await org_service.db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await org_service.join_by_code(
            code=org.invitation_code,
            user_id="user-789",
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "INVALID_INVITATION_CODE"


@pytest.mark.asyncio
async def test_join_by_invalid_code_fails(org_service):
    """Code inexistant → 404 avec message identique à code expiré (pas d'énumération)."""
    with pytest.raises(HTTPException) as exc_info:
        await org_service.join_by_code(
            code="XXXXXXXX",
            user_id="user-000",
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "INVALID_INVITATION_CODE"


@pytest.mark.asyncio
async def test_join_when_already_member_fails(org_service):
    """Un utilisateur déjà membre ne peut pas rejoindre 2 fois."""
    org_id = await _create_org(org_service)
    code_result = await org_service.generate_invitation_code(
        org_id, GenerateInvitationCodeRequest(expires_in_days=30)
    )

    # Premier join — succès
    await org_service.join_by_code(
        code=code_result.invitation_code,
        user_id="user-dup",
    )

    # Deuxième join — 409
    with pytest.raises(HTTPException) as exc_info:
        await org_service.join_by_code(
            code=code_result.invitation_code,
            user_id="user-dup",
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "ALREADY_MEMBER"


# ── Get User Organizations ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_user_organizations(org_service):
    """Lister les organisations d'un utilisateur."""
    org1 = await _create_org(org_service, slug="bcb", name="BCB")
    org2 = await _create_org(org_service, slug="hopital", name="Hopital")

    code1 = await org_service.generate_invitation_code(org1, GenerateInvitationCodeRequest())
    code2 = await org_service.generate_invitation_code(org2, GenerateInvitationCodeRequest())

    await org_service.join_by_code(code=code1.invitation_code, user_id="user-multi")
    await org_service.join_by_code(code=code2.invitation_code, user_id="user-multi")

    result = await org_service.get_user_organizations("user-multi")
    assert result.total == 2
    org_ids = [item.organization_id for item in result.items]
    assert org1 in org_ids
    assert org2 in org_ids


# ── Leave Organization ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_leave_organization(org_service):
    """Un utilisateur peut quitter une organisation."""
    org_id = await _create_org(org_service)
    code_result = await org_service.generate_invitation_code(
        org_id, GenerateInvitationCodeRequest()
    )
    await org_service.join_by_code(code=code_result.invitation_code, user_id="user-leave")

    await org_service.leave_organization("user-leave", org_id)

    # L'appartenance est inactive — n'apparaît plus dans la liste
    result = await org_service.get_user_organizations("user-leave")
    assert result.total == 0


@pytest.mark.asyncio
async def test_leave_organization_not_member_raises_404(org_service):
    """Quitter une org où on n'est pas membre → 404."""
    org_id = await _create_org(org_service)

    with pytest.raises(HTTPException) as exc_info:
        await org_service.leave_organization("user-nobody", org_id)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "MEMBERSHIP_NOT_FOUND"
