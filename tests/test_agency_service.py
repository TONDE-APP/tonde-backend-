"""
Tests unitaires — AgencyService

Couvre : create, get_by_id, list, update, delete (soft)
+ contraintes d'accès org_id (isolation multi-tenant)
"""
import pytest
from fastapi import HTTPException

from app.services.agency_service import AgencyService
from app.services.organization_service import OrganizationService
from app.schemas.agency import CreateAgencyRequest, UpdateAgencyRequest
from app.schemas.organization import CreateOrganizationRequest


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def agency_service(db_session):
    return AgencyService(db_session)


@pytest.fixture
def org_service(db_session):
    return OrganizationService(db_session)


async def _create_org(org_service, slug="bcb", name="BCB") -> str:
    """Helper : crée une org et retourne son ID."""
    org = await org_service.create(CreateOrganizationRequest(
        name=name, slug=slug, sector="bank"
    ))
    return org.id


def _make_agency_data(**overrides) -> CreateAgencyRequest:
    defaults = {
        "name": "Agence Centre",
        "slug": "bcb-centre",
        "sector": "bank",
        "city": "Bujumbura",
    }
    defaults.update(overrides)
    return CreateAgencyRequest(**defaults)


# ── Create ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_agency_success(agency_service, org_service):
    org_id = await _create_org(org_service)
    result = await agency_service.create(org_id, _make_agency_data(), caller_org_id=org_id)

    assert result.name == "Agence Centre"
    assert result.org_id == org_id
    assert result.is_active is True
    assert result.is_open is False


@pytest.mark.asyncio
async def test_create_agency_wrong_org_raises_403(agency_service, org_service):
    org_id = await _create_org(org_service)
    other_org_id = await _create_org(org_service, slug="hopital", name="Hopital")

    with pytest.raises(HTTPException) as exc_info:
        # Un admin de org_id tente de créer dans other_org_id
        await agency_service.create(other_org_id, _make_agency_data(), caller_org_id=org_id)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_create_agency_super_admin_can_create_anywhere(agency_service, org_service):
    org_id = await _create_org(org_service)
    # super_admin passe caller_org_id=None
    result = await agency_service.create(org_id, _make_agency_data(), caller_org_id=None)
    assert result.org_id == org_id


@pytest.mark.asyncio
async def test_create_agency_org_not_found_raises_404(agency_service):
    with pytest.raises(HTTPException) as exc_info:
        await agency_service.create("bad-org-id", _make_agency_data(), caller_org_id=None)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "ORG_NOT_FOUND"


@pytest.mark.asyncio
async def test_create_agency_duplicate_slug_raises_409(agency_service, org_service):
    org_id = await _create_org(org_service)
    await agency_service.create(org_id, _make_agency_data(), caller_org_id=None)

    with pytest.raises(HTTPException) as exc_info:
        await agency_service.create(org_id, _make_agency_data(name="Autre agence"), caller_org_id=None)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "SLUG_TAKEN"


# ── Get by ID ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_agency_by_id_success(agency_service, org_service):
    org_id = await _create_org(org_service)
    created = await agency_service.create(org_id, _make_agency_data(), caller_org_id=None)

    result = await agency_service.get_by_id(created.id, caller_org_id=org_id)
    assert result.id == created.id


@pytest.mark.asyncio
async def test_get_agency_wrong_org_raises_404(agency_service, org_service):
    org_id = await _create_org(org_service)
    other_org_id = await _create_org(org_service, slug="hopital", name="Hopital")
    created = await agency_service.create(org_id, _make_agency_data(), caller_org_id=None)

    # Un admin d'other_org tente de lire une agence de org
    with pytest.raises(HTTPException) as exc_info:
        await agency_service.get_by_id(created.id, caller_org_id=other_org_id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_agency_not_found_raises_404(agency_service):
    with pytest.raises(HTTPException) as exc_info:
        await agency_service.get_by_id("bad-id", caller_org_id=None)
    assert exc_info.value.status_code == 404


# ── List ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_agencies_filtered_by_org(agency_service, org_service):
    org1 = await _create_org(org_service, slug="bcb", name="BCB")
    org2 = await _create_org(org_service, slug="hopital", name="Hopital")

    await agency_service.create(org1, _make_agency_data(slug="bcb-centre"), caller_org_id=None)
    await agency_service.create(org1, _make_agency_data(name="BCB Ngagara", slug="bcb-ngagara"), caller_org_id=None)
    await agency_service.create(org2, _make_agency_data(name="Hopital Urgences", slug="hopital-urgences"), caller_org_id=None)

    # L'admin de BCB ne voit que ses 2 agences
    result = await agency_service.list(caller_org_id=org1)
    assert result.total == 2

    # L'admin de l'hôpital ne voit que son agence
    result2 = await agency_service.list(caller_org_id=org2)
    assert result2.total == 1


@pytest.mark.asyncio
async def test_list_agencies_super_admin_sees_all(agency_service, org_service):
    org1 = await _create_org(org_service, slug="bcb", name="BCB")
    org2 = await _create_org(org_service, slug="hopital", name="Hopital")

    await agency_service.create(org1, _make_agency_data(slug="bcb-centre"), caller_org_id=None)
    await agency_service.create(org2, _make_agency_data(name="Hopital", slug="hopital-centre"), caller_org_id=None)

    result = await agency_service.list(caller_org_id=None)
    assert result.total == 2


# ── Update ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_update_agency_success(agency_service, org_service):
    org_id = await _create_org(org_service)
    created = await agency_service.create(org_id, _make_agency_data(), caller_org_id=None)

    updated = await agency_service.update(
        created.id,
        UpdateAgencyRequest(name="Agence Centre Modifiée", opens_at="09:00"),
        caller_org_id=org_id,
    )
    assert updated.name == "Agence Centre Modifiée"
    assert updated.opens_at == "09:00"


@pytest.mark.asyncio
async def test_update_agency_wrong_org_raises_404(agency_service, org_service):
    org_id = await _create_org(org_service)
    other_org_id = await _create_org(org_service, slug="hopital", name="Hopital")
    created = await agency_service.create(org_id, _make_agency_data(), caller_org_id=None)

    with pytest.raises(HTTPException) as exc_info:
        await agency_service.update(created.id, UpdateAgencyRequest(name="Hack"), caller_org_id=other_org_id)
    assert exc_info.value.status_code == 404


# ── Delete (soft) ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_delete_agency_soft_delete(agency_service, org_service):
    org_id = await _create_org(org_service)
    created = await agency_service.create(org_id, _make_agency_data(), caller_org_id=None)

    await agency_service.delete(created.id, caller_org_id=org_id)

    result = await agency_service.get_by_id(created.id, caller_org_id=org_id)
    assert result.is_active is False


@pytest.mark.asyncio
async def test_delete_agency_wrong_org_raises_404(agency_service, org_service):
    org_id = await _create_org(org_service)
    other_org_id = await _create_org(org_service, slug="hopital", name="Hopital")
    created = await agency_service.create(org_id, _make_agency_data(), caller_org_id=None)

    with pytest.raises(HTTPException) as exc_info:
        await agency_service.delete(created.id, caller_org_id=other_org_id)
    assert exc_info.value.status_code == 404
