"""
Tests unitaires — CounterService

Couvre :
  - Création : cas nominal, unicité du nom, agence invalide
  - Get by ID : cas nominal, isolation multi-tenant
  - List : filtrage par agence, pagination
  - Update : cas nominal, guichet introuvable
  - Open / Close : transitions et erreurs
  - Delete (soft) : désactivation
  - Isolation multi-tenant : org A ne voit pas les guichets d'org B
"""
import pytest
from fastapi import HTTPException

from app.services.counter_service import CounterService
from app.services.organization_service import OrganizationService
from app.services.agency_service import AgencyService
from app.schemas.counter import CreateCounterRequest, UpdateCounterRequest
from app.schemas.organization import CreateOrganizationRequest
from app.schemas.agency import CreateAgencyRequest


# ── Fixtures helpers ──────────────────────────────────────────────────────────

@pytest.fixture
def counter_service(db_session):
    return CounterService(db_session)


@pytest.fixture
def org_service(db_session):
    return OrganizationService(db_session)


@pytest.fixture
def agency_service(db_session):
    return AgencyService(db_session)


async def _create_org(org_service, slug: str = "bcb", name: str = "BCB") -> str:
    org = await org_service.create(CreateOrganizationRequest(
        name=name, slug=slug, sector="bank"
    ))
    return org.id


async def _create_agency(agency_service, org_id: str, slug: str = "bcb-centre") -> str:
    agency = await agency_service.create(
        org_id,
        CreateAgencyRequest(name="Agence Centre", slug=slug, sector="bank"),
        caller_org_id=None,
    )
    # Ouvrir l'agence pour qu'elle soit is_active=True
    return agency.id


def _counter_data(**overrides) -> CreateCounterRequest:
    defaults = {"name": "Guichet 1"}
    defaults.update(overrides)
    return CreateCounterRequest(**defaults)


# ── Create ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_counter_success(counter_service, org_service, agency_service):
    """Création d'un guichet dans le cas nominal."""
    org_id = await _create_org(org_service)
    agency_id = await _create_agency(agency_service, org_id)

    result = await counter_service.create(org_id, agency_id, _counter_data())

    assert result.name == "Guichet 1"
    assert result.org_id == org_id
    assert result.agency_id == agency_id
    assert result.is_open is False
    assert result.is_active is True


@pytest.mark.asyncio
async def test_create_counter_wrong_org_raises_404(counter_service, org_service, agency_service):
    """Agence d'une autre org → HTTP 404 (isolation multi-tenant)."""
    org_a = await _create_org(org_service, slug="org-a", name="Org A")
    org_b = await _create_org(org_service, slug="org-b", name="Org B")
    agency_id = await _create_agency(agency_service, org_a)

    with pytest.raises(HTTPException) as exc_info:
        await counter_service.create(org_b, agency_id, _counter_data())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "AGENCY_NOT_FOUND"


@pytest.mark.asyncio
async def test_create_counter_duplicate_name_raises_409(counter_service, org_service, agency_service):
    """Deux guichets avec le même nom dans la même agence → HTTP 409."""
    org_id = await _create_org(org_service)
    agency_id = await _create_agency(agency_service, org_id)

    await counter_service.create(org_id, agency_id, _counter_data(name="Guichet Caisse"))

    with pytest.raises(HTTPException) as exc_info:
        await counter_service.create(org_id, agency_id, _counter_data(name="Guichet Caisse"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "COUNTER_NAME_TAKEN"


@pytest.mark.asyncio
async def test_create_counter_invalid_agency_raises_404(counter_service, org_service):
    """Agence inexistante → HTTP 404."""
    org_id = await _create_org(org_service)

    with pytest.raises(HTTPException) as exc_info:
        await counter_service.create(org_id, "bad-agency-id", _counter_data())

    assert exc_info.value.status_code == 404


# ── Get by ID ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_counter_by_id_success(counter_service, org_service, agency_service):
    """Récupère un guichet par son ID."""
    org_id = await _create_org(org_service)
    agency_id = await _create_agency(agency_service, org_id)
    created = await counter_service.create(org_id, agency_id, _counter_data())

    result = await counter_service.get_by_id(created.id, org_id)
    assert result.id == created.id
    assert result.name == "Guichet 1"


@pytest.mark.asyncio
async def test_get_counter_wrong_org_raises_404(counter_service, org_service, agency_service):
    """Un admin d'org B ne peut pas voir un guichet d'org A."""
    org_a = await _create_org(org_service, slug="org-a", name="Org A")
    org_b = await _create_org(org_service, slug="org-b", name="Org B")
    agency_id = await _create_agency(agency_service, org_a)
    created = await counter_service.create(org_a, agency_id, _counter_data())

    with pytest.raises(HTTPException) as exc_info:
        await counter_service.get_by_id(created.id, org_b)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "COUNTER_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_counter_not_found_raises_404(counter_service, org_service):
    """ID inexistant → HTTP 404."""
    org_id = await _create_org(org_service)

    with pytest.raises(HTTPException) as exc_info:
        await counter_service.get_by_id("bad-id", org_id)

    assert exc_info.value.status_code == 404


# ── List ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_counters_filtered_by_agency(counter_service, org_service, agency_service):
    """list() retourne uniquement les guichets de l'agence demandée."""
    org_id = await _create_org(org_service)
    agency_a = await _create_agency(agency_service, org_id, slug="agence-a")
    agency_b = await _create_agency(agency_service, org_id, slug="agence-b")

    await counter_service.create(org_id, agency_a, _counter_data(name="G1"))
    await counter_service.create(org_id, agency_a, _counter_data(name="G2"))
    await counter_service.create(org_id, agency_b, _counter_data(name="G3"))

    result = await counter_service.list(org_id, agency_a)
    assert result.total == 2

    result_b = await counter_service.list(org_id, agency_b)
    assert result_b.total == 1


@pytest.mark.asyncio
async def test_list_counters_wrong_org_raises_404(counter_service, org_service, agency_service):
    """list() avec mauvaise org → HTTP 404 (agence n'appartient pas à l'org)."""
    org_a = await _create_org(org_service, slug="org-a", name="Org A")
    org_b = await _create_org(org_service, slug="org-b", name="Org B")
    agency_id = await _create_agency(agency_service, org_a)

    with pytest.raises(HTTPException) as exc_info:
        await counter_service.list(org_b, agency_id)

    assert exc_info.value.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_counter_success(counter_service, org_service, agency_service):
    """Mise à jour du nom d'un guichet."""
    org_id = await _create_org(org_service)
    agency_id = await _create_agency(agency_service, org_id)
    created = await counter_service.create(org_id, agency_id, _counter_data())

    updated = await counter_service.update(
        created.id, org_id,
        UpdateCounterRequest(name="Guichet VIP", description="Guichet prioritaire")
    )

    assert updated.name == "Guichet VIP"
    assert updated.description == "Guichet prioritaire"


@pytest.mark.asyncio
async def test_update_counter_wrong_org_raises_404(counter_service, org_service, agency_service):
    """Un admin d'org B ne peut pas modifier un guichet d'org A."""
    org_a = await _create_org(org_service, slug="org-a", name="Org A")
    org_b = await _create_org(org_service, slug="org-b", name="Org B")
    agency_id = await _create_agency(agency_service, org_a)
    created = await counter_service.create(org_a, agency_id, _counter_data())

    with pytest.raises(HTTPException) as exc_info:
        await counter_service.update(created.id, org_b, UpdateCounterRequest(name="Hack"))

    assert exc_info.value.status_code == 404


# ── Open / Close ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_open_counter_success(counter_service, org_service, agency_service):
    """Ouverture d'un guichet fermé."""
    org_id = await _create_org(org_service)
    agency_id = await _create_agency(agency_service, org_id)
    created = await counter_service.create(org_id, agency_id, _counter_data())
    assert created.is_open is False

    opened = await counter_service.open(created.id, org_id)
    assert opened.is_open is True


@pytest.mark.asyncio
async def test_open_already_open_raises_400(counter_service, org_service, agency_service):
    """Ouvrir un guichet déjà ouvert → HTTP 400."""
    org_id = await _create_org(org_service)
    agency_id = await _create_agency(agency_service, org_id)
    created = await counter_service.create(org_id, agency_id, _counter_data())
    await counter_service.open(created.id, org_id)

    with pytest.raises(HTTPException) as exc_info:
        await counter_service.open(created.id, org_id)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "COUNTER_ALREADY_OPEN"


@pytest.mark.asyncio
async def test_close_counter_success(counter_service, org_service, agency_service):
    """Fermeture d'un guichet ouvert."""
    org_id = await _create_org(org_service)
    agency_id = await _create_agency(agency_service, org_id)
    created = await counter_service.create(org_id, agency_id, _counter_data())
    await counter_service.open(created.id, org_id)

    closed = await counter_service.close(created.id, org_id)
    assert closed.is_open is False


@pytest.mark.asyncio
async def test_close_already_closed_raises_400(counter_service, org_service, agency_service):
    """Fermer un guichet déjà fermé → HTTP 400."""
    org_id = await _create_org(org_service)
    agency_id = await _create_agency(agency_service, org_id)
    created = await counter_service.create(org_id, agency_id, _counter_data())

    with pytest.raises(HTTPException) as exc_info:
        await counter_service.close(created.id, org_id)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "COUNTER_ALREADY_CLOSED"


# ── Delete (soft) ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_counter_soft_delete(counter_service, org_service, agency_service):
    """Suppression douce — le guichet est désactivé, pas supprimé."""
    org_id = await _create_org(org_service)
    agency_id = await _create_agency(agency_service, org_id)
    created = await counter_service.create(org_id, agency_id, _counter_data())

    await counter_service.delete(created.id, org_id)

    result = await counter_service.get_by_id(created.id, org_id)
    assert result.is_active is False
    assert result.is_open is False


@pytest.mark.asyncio
async def test_delete_counter_wrong_org_raises_404(counter_service, org_service, agency_service):
    """Un admin d'org B ne peut pas supprimer un guichet d'org A."""
    org_a = await _create_org(org_service, slug="org-a", name="Org A")
    org_b = await _create_org(org_service, slug="org-b", name="Org B")
    agency_id = await _create_agency(agency_service, org_a)
    created = await counter_service.create(org_a, agency_id, _counter_data())

    with pytest.raises(HTTPException) as exc_info:
        await counter_service.delete(created.id, org_b)

    assert exc_info.value.status_code == 404
