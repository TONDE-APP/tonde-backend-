"""
Tests unitaires — TicketService (Queue Engine)

Couvre :
  - Création de ticket : cas nominal
  - Création : agence fermée → 400
  - Création : ticket actif existant → 409
  - Annulation : cas nominal
  - Annulation : ticket d'un autre user → 403
  - Machine à états : transitions autorisées
  - Machine à états : transitions interdites → 400
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException

from app.models.organization import Organization
from app.models.agency import Agency, Service
from app.models.ticket import TicketStatus, TicketPriority
from app.schemas.ticket import CreateTicketRequest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_queue(mock_redis):
    """Mock des helpers Redis de file d'attente."""
    with patch("app.services.ticket_service.add_to_queue", new_callable=AsyncMock, return_value=1):
        with patch("app.services.ticket_service.get_queue_size", new_callable=AsyncMock, return_value=1):
            with patch("app.services.ticket_service.remove_from_queue", new_callable=AsyncMock):
                with patch("app.services.ticket_service.get_next_ticket", new_callable=AsyncMock):
                    with patch("app.services.ticket_service.get_queue_position", new_callable=AsyncMock, return_value=1):
                        yield


async def _create_test_org(db_session) -> Organization:
    """Crée une organisation de test."""
    org = Organization(
        name="Banque Test Burundi",
        slug="banque-test-bi",
        sector="bank",
        country="Burundi",
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


async def _create_test_agency(db_session, org_id: str, is_open: bool = True) -> Agency:
    """Crée une agence de test."""
    agency = Agency(
        org_id=org_id,
        name="Agence Centre-ville",
        slug=f"agence-centre-{org_id[:8]}",
        sector="bank",
        is_active=True,
        is_open=is_open,
    )
    db_session.add(agency)
    await db_session.commit()
    await db_session.refresh(agency)
    return agency


async def _create_test_service(db_session, agency_id: str, org_id: str) -> Service:
    """Crée un service de test."""
    service = Service(
        org_id=org_id,
        agency_id=agency_id,
        name="Dépôt",
        ticket_prefix="A",
        avg_duration_minutes=5,
    )
    db_session.add(service)
    await db_session.commit()
    await db_session.refresh(service)
    return service


# ── Tests création ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_ticket_success(ticket_service, db_session, mock_queue):
    """Création de ticket dans le cas nominal."""
    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)

    result = await ticket_service.create_ticket(
        CreateTicketRequest(
            agency_id=agency.id,
            service_id=service.id,
            priority="standard",
        ),
        user_id="user-test-123",
        org_id=org.id,
    )

    assert result.number == "A-1"
    assert result.status == "waiting"
    assert result.priority == "standard"
    assert result.position == 1


@pytest.mark.asyncio
async def test_create_ticket_agency_closed_raises_400(ticket_service, db_session, mock_queue):
    """Agence fermée → HTTP 400."""
    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id, is_open=False)
    service = await _create_test_service(db_session, agency.id, org.id)

    with pytest.raises(HTTPException) as exc_info:
        await ticket_service.create_ticket(
            CreateTicketRequest(
                agency_id=agency.id,
                service_id=service.id,
            ),
            user_id="user-test-123",
            org_id=org.id,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "AGENCY_CLOSED"


@pytest.mark.asyncio
async def test_create_ticket_duplicate_raises_409(ticket_service, db_session, mock_queue):
    """Un ticket actif existe déjà → HTTP 409."""
    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)
    user_id = "user-dup-test"

    # Premier ticket
    await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id=user_id,
        org_id=org.id,
    )

    # Deuxième ticket → conflit
    with pytest.raises(HTTPException) as exc_info:
        await ticket_service.create_ticket(
            CreateTicketRequest(agency_id=agency.id, service_id=service.id),
            user_id=user_id,
            org_id=org.id,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "TICKET_EXISTS"


@pytest.mark.asyncio
async def test_create_ticket_wrong_org_raises_404(ticket_service, db_session, mock_queue):
    """Agence d'une autre organisation → 404 (isolation multi-tenant)."""
    org_a = await _create_test_org(db_session)
    # org_b simule une autre organisation
    org_b = Organization(name="Org B", slug="org-b", sector="hospital")
    db_session.add(org_b)
    await db_session.commit()
    await db_session.refresh(org_b)

    agency = await _create_test_agency(db_session, org_a.id)
    service = await _create_test_service(db_session, agency.id, org_a.id)

    with pytest.raises(HTTPException) as exc_info:
        await ticket_service.create_ticket(
            CreateTicketRequest(agency_id=agency.id, service_id=service.id),
            user_id="user-test",
            org_id=org_b.id,  # ← mauvaise org
        )

    assert exc_info.value.status_code == 404


# ── Tests annulation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_ticket_success(ticket_service, db_session, mock_queue):
    """Annulation d'un ticket WAITING réussit."""
    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)
    user_id = "user-cancel-test"

    ticket = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id=user_id,
        org_id=org.id,
    )

    result = await ticket_service.cancel_ticket(ticket.id, user_id, org.id)
    assert result["success"] is True


@pytest.mark.asyncio
async def test_cancel_ticket_wrong_user_raises_403(ticket_service, db_session, mock_queue):
    """Annulation par un autre utilisateur → HTTP 403."""
    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)

    ticket = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id="owner-user",
        org_id=org.id,
    )

    with pytest.raises(HTTPException) as exc_info:
        await ticket_service.cancel_ticket(ticket.id, "other-user", org.id)

    assert exc_info.value.status_code == 403


# ── Tests machine à états ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_state_machine_waiting_to_called(ticket_service, db_session, mock_queue):
    """Transition WAITING → CALLED autorisée."""
    from app.models.ticket import Ticket

    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)

    ticket_resp = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id="user-fsm",
        org_id=org.id,
    )

    # Récupérer le vrai objet Ticket
    from sqlalchemy import select
    result = await db_session.execute(
        select(Ticket).where(Ticket.id == ticket_resp.id)
    )
    ticket = result.scalar_one()

    # La transition doit réussir sans exception
    await ticket_service._transition(ticket, TicketStatus.CALLED)
    assert ticket.status == TicketStatus.CALLED


@pytest.mark.asyncio
async def test_state_machine_invalid_transition_raises_400(ticket_service, db_session, mock_queue):
    """Transition interdite → HTTP 400 avec message explicite."""
    from app.models.ticket import Ticket
    from sqlalchemy import select

    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)

    ticket_resp = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id="user-fsm-invalid",
        org_id=org.id,
    )

    result = await db_session.execute(
        select(Ticket).where(Ticket.id == ticket_resp.id)
    )
    ticket = result.scalar_one()

    # WAITING → DONE est interdit (doit passer par CALLED → SERVING → DONE)
    with pytest.raises(HTTPException) as exc_info:
        await ticket_service._transition(ticket, TicketStatus.DONE)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_TRANSITION"


@pytest.mark.asyncio
async def test_state_machine_terminal_states_are_blocked(ticket_service, db_session, mock_queue):
    """Les états terminaux (DONE, CANCELLED) n'autorisent aucune transition."""
    from app.models.ticket import Ticket, ALLOWED_TRANSITIONS

    terminal_states = [
        TicketStatus.DONE,
        TicketStatus.CANCELLED,
        TicketStatus.INCOMPLETE,
        TicketStatus.TRANSFERRED,
    ]

    for state in terminal_states:
        assert ALLOWED_TRANSITIONS[state] == [], \
            f"L'état {state} devrait être terminal (aucune transition autorisée)"
