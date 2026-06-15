"""
Tests unitaires — OrganizationService

Couvre : create, get_by_id, list, update, delete (soft)
"""
import pytest
from fastapi import HTTPException

from app.services.organization_service import OrganizationService
from app.schemas.organization import CreateOrganizationRequest, UpdateOrganizationRequest


# ── Fixture ───────────────────────────────────────────────────────────────────
@pytest.fixture
def org_service(db_session):
    return OrganizationService(db_session)


def _make_create_data(**overrides) -> CreateOrganizationRequest:
    defaults = {
        "name": "Banque BCB",
        "slug": "bcb-burundi",
        "sector": "bank",
        "country": "Burundi",
        "city": "Bujumbura",
    }
    defaults.update(overrides)
    return CreateOrganizationRequest(**defaults)


# ── Create ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_organization_success(org_service):
    data = _make_create_data()
    result = await org_service.create(data)

    assert result.name == "Banque BCB"
    assert result.slug == "bcb-burundi"
    assert result.sector == "bank"
    assert result.is_active is True
    assert result.id is not None


@pytest.mark.asyncio
async def test_create_organization_duplicate_slug_raises_409(org_service):
    data = _make_create_data()
    await org_service.create(data)

    with pytest.raises(HTTPException) as exc_info:
        await org_service.create(_make_create_data(name="Autre banque"))
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "SLUG_TAKEN"


# ── Get by ID ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_organization_by_id_success(org_service):
    created = await org_service.create(_make_create_data())
    result = await org_service.get_by_id(created.id)

    assert result.id == created.id
    assert result.name == created.name


@pytest.mark.asyncio
async def test_get_organization_not_found_raises_404(org_service):
    with pytest.raises(HTTPException) as exc_info:
        await org_service.get_by_id("non-existent-id")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "ORG_NOT_FOUND"


# ── List ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_organizations_returns_all(org_service):
    await org_service.create(_make_create_data(name="BCB", slug="bcb"))
    await org_service.create(_make_create_data(name="Hopital", slug="hopital", sector="hospital"))

    result = await org_service.list(page=1, page_size=20)
    assert result.total == 2
    assert len(result.items) == 2


@pytest.mark.asyncio
async def test_list_organizations_active_only(org_service):
    created = await org_service.create(_make_create_data(slug="bcb-active"))
    await org_service.create(_make_create_data(name="Inactive", slug="bcb-inactive"))
    # Désactiver la deuxième
    await org_service.delete(created.id)

    result = await org_service.list(active_only=True)
    assert result.total == 1


@pytest.mark.asyncio
async def test_list_organizations_pagination(org_service):
    for i in range(5):
        await org_service.create(_make_create_data(name=f"Org {i}", slug=f"org-{i}"))

    page1 = await org_service.list(page=1, page_size=3)
    page2 = await org_service.list(page=2, page_size=3)

    assert len(page1.items) == 3
    assert len(page2.items) == 2
    assert page1.total == 5


# ── Update ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_update_organization_success(org_service):
    created = await org_service.create(_make_create_data())
    updated = await org_service.update(
        created.id,
        UpdateOrganizationRequest(name="BCB Nouveau Nom", city="Ngagara")
    )

    assert updated.name == "BCB Nouveau Nom"
    assert updated.city == "Ngagara"
    assert updated.slug == created.slug  # slug inchangé


@pytest.mark.asyncio
async def test_update_organization_not_found_raises_404(org_service):
    with pytest.raises(HTTPException) as exc_info:
        await org_service.update("bad-id", UpdateOrganizationRequest(name="Test"))
    assert exc_info.value.status_code == 404


# ── Delete (soft) ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_delete_organization_soft_delete(org_service):
    created = await org_service.create(_make_create_data())
    await org_service.delete(created.id)

    # L'org existe toujours en base mais est inactive
    result = await org_service.get_by_id(created.id)
    assert result.is_active is False


@pytest.mark.asyncio
async def test_delete_organization_not_found_raises_404(org_service):
    with pytest.raises(HTTPException) as exc_info:
        await org_service.delete("bad-id")
    assert exc_info.value.status_code == 404
