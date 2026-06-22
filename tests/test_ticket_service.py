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
    """Mock des helpers Redis de file d'attente — signatures avec service_id (TASK-04)."""
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
    """Un ticket actif existe déjà → HTTP 409 avec code TICKET_ALREADY_ACTIVE et active_ticket_id."""
    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)
    user_id = "user-dup-test"

    # Premier ticket
    first = await ticket_service.create_ticket(
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
    assert exc_info.value.detail["code"] == "TICKET_ALREADY_ACTIVE"
    # Le mobile peut rediriger vers le ticket actif grâce à ces champs
    assert exc_info.value.detail["active_ticket_id"] == first.id
    assert exc_info.value.detail["active_ticket_number"] == first.number


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


# ── TASK-03 : tests règle "1 ticket actif global" ─────────────────────────────

@pytest.mark.asyncio
async def test_active_statuses_constant():
    """ACTIVE_STATUSES contient exactement les 6 statuts bloquants attendus."""
    from app.services.ticket_service import ACTIVE_STATUSES

    expected = {
        TicketStatus.WAITING,
        TicketStatus.CALLED,
        TicketStatus.SERVING,
        TicketStatus.ABSENT,
        TicketStatus.TRANSFERRED,
        TicketStatus.INCOMPLETE,
    }
    assert set(ACTIVE_STATUSES) == expected


@pytest.mark.asyncio
async def test_one_active_ticket_global_rule(ticket_service, db_session, mock_queue):
    """Un user avec ticket WAITING dans agence A ne peut pas prendre un ticket dans agence B."""
    org = await _create_test_org(db_session)
    agency_a = await _create_test_agency(db_session, org.id)
    agency_b = Agency(
        org_id=org.id,
        name="Agence B",
        slug=f"agence-b-{org.id[:8]}",
        sector="bank",
        is_active=True,
        is_open=True,
    )
    db_session.add(agency_b)
    await db_session.commit()
    await db_session.refresh(agency_b)

    service_a = await _create_test_service(db_session, agency_a.id, org.id)
    service_b = await _create_test_service(db_session, agency_b.id, org.id)

    user_id = "user-global-rule"

    # Premier ticket dans agence A
    first = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency_a.id, service_id=service_a.id),
        user_id=user_id,
        org_id=org.id,
    )
    assert first.status == "waiting"

    # Deuxième ticket dans agence B → doit être bloqué globalement
    with pytest.raises(HTTPException) as exc_info:
        await ticket_service.create_ticket(
            CreateTicketRequest(agency_id=agency_b.id, service_id=service_b.id),
            user_id=user_id,
            org_id=org.id,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "TICKET_ALREADY_ACTIVE"


@pytest.mark.asyncio
async def test_ticket_allowed_after_cancel(ticket_service, db_session, mock_queue):
    """Après annulation (CANCELLED), l'user peut prendre un nouveau ticket."""
    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)
    user_id = "user-after-cancel"

    # Premier ticket puis annulation
    first = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id=user_id,
        org_id=org.id,
    )
    await ticket_service.cancel_ticket(first.id, user_id, org.id)

    # Nouveau ticket doit réussir
    second = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id=user_id,
        org_id=org.id,
    )
    assert second.status == "waiting"


@pytest.mark.asyncio
async def test_ticket_allowed_after_done(ticket_service, db_session, mock_queue):
    """Après DONE, l'user peut prendre un nouveau ticket."""
    from app.models.ticket import Ticket
    from sqlalchemy import select as sa_select

    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)
    user_id = "user-after-done"

    first_resp = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id=user_id,
        org_id=org.id,
    )

    # Faire passer le ticket jusqu'à DONE via la machine à états
    result = await db_session.execute(sa_select(Ticket).where(Ticket.id == first_resp.id))
    ticket = result.scalar_one()
    await ticket_service._transition(ticket, TicketStatus.CALLED)
    await ticket_service._transition(ticket, TicketStatus.SERVING)
    await ticket_service._transition(ticket, TicketStatus.DONE)
    await db_session.commit()

    # Nouveau ticket doit réussir
    second = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id=user_id,
        org_id=org.id,
    )
    assert second.status == "waiting"


@pytest.mark.asyncio
async def test_absent_ticket_blocks_new_ticket(ticket_service, db_session, mock_queue):
    """Un ticket en statut ABSENT bloque la création d'un nouveau ticket."""
    from app.models.ticket import Ticket
    from sqlalchemy import select as sa_select

    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)
    user_id = "user-absent-test"

    first_resp = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id=user_id,
        org_id=org.id,
    )

    # Faire passer le ticket en ABSENT
    result = await db_session.execute(sa_select(Ticket).where(Ticket.id == first_resp.id))
    ticket = result.scalar_one()
    await ticket_service._transition(ticket, TicketStatus.CALLED)
    await ticket_service._transition(ticket, TicketStatus.ABSENT)
    await db_session.commit()

    # Nouveau ticket doit être bloqué (ABSENT est dans ACTIVE_STATUSES)
    with pytest.raises(HTTPException) as exc_info:
        await ticket_service.create_ticket(
            CreateTicketRequest(agency_id=agency.id, service_id=service.id),
            user_id=user_id,
            org_id=org.id,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "TICKET_ALREADY_ACTIVE"


@pytest.mark.asyncio
async def test_409_includes_active_ticket_id(ticket_service, db_session, mock_queue):
    """La réponse 409 contient active_ticket_id et active_ticket_number pour la redirection mobile."""
    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)
    user_id = "user-409-fields"

    first = await ticket_service.create_ticket(
        CreateTicketRequest(agency_id=agency.id, service_id=service.id),
        user_id=user_id,
        org_id=org.id,
    )

    with pytest.raises(HTTPException) as exc_info:
        await ticket_service.create_ticket(
            CreateTicketRequest(agency_id=agency.id, service_id=service.id),
            user_id=user_id,
            org_id=org.id,
        )

    detail = exc_info.value.detail
    assert detail["code"] == "TICKET_ALREADY_ACTIVE"
    assert detail["active_ticket_id"] == first.id
    assert detail["active_ticket_number"] == first.number
    assert "message" in detail


# ── TASK-04 : tests clés Redis segmentées par service ─────────────────────────

def test_queue_key_includes_service_id():
    """_queue_key() produit exactement tonde:{org}:{agency}:{service}:queue."""
    from app.core.redis import _queue_key

    key = _queue_key("org-1", "agency-1", "service-1")
    assert key == "tonde:org-1:agency-1:service-1:queue"


def test_two_services_have_independent_queues():
    """Deux service_id différents produisent des clés Redis distinctes."""
    from app.core.redis import _queue_key

    key_a = _queue_key("org-1", "agency-1", "caisse")
    key_b = _queue_key("org-1", "agency-1", "credit")

    assert key_a != key_b
    assert "caisse" in key_a
    assert "credit" in key_b


def test_queue_key_format_with_various_ids():
    """_queue_key() est déterministe et inclut les 3 segments."""
    from app.core.redis import _queue_key

    org = "org-abc"
    agency = "agency-xyz"
    service = "service-123"

    key = _queue_key(org, agency, service)

    assert key.startswith("tonde:")
    assert key.endswith(":queue")
    assert org in key
    assert agency in key
    assert service in key


@pytest.mark.asyncio
async def test_create_ticket_passes_service_id_to_redis(ticket_service, db_session, mock_redis):
    """create_ticket() passe ticket.service_id à add_to_queue()."""
    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)

    with patch("app.services.ticket_service.add_to_queue", new_callable=AsyncMock, return_value=1) as mock_add:
        with patch("app.services.ticket_service.get_queue_size", new_callable=AsyncMock, return_value=1):
            await ticket_service.create_ticket(
                CreateTicketRequest(agency_id=agency.id, service_id=service.id),
                user_id="user-redis-test",
                org_id=org.id,
            )

    # Vérifier que service_id est bien passé à add_to_queue
    call_args = mock_add.call_args
    assert call_args is not None
    # Signature : add_to_queue(org_id, agency_id, service_id, ticket_id, priority_score)
    positional = call_args.args
    assert len(positional) >= 3
    assert positional[2] == service.id, "service_id doit être le 3ème argument de add_to_queue"


@pytest.mark.asyncio
async def test_cancel_ticket_passes_service_id_to_remove_from_queue(ticket_service, db_session, mock_redis):
    """cancel_ticket() passe ticket.service_id à remove_from_queue()."""
    org = await _create_test_org(db_session)
    agency = await _create_test_agency(db_session, org.id)
    service = await _create_test_service(db_session, agency.id, org.id)
    user_id = "user-cancel-redis"

    with patch("app.services.ticket_service.add_to_queue", new_callable=AsyncMock, return_value=1):
        with patch("app.services.ticket_service.get_queue_size", new_callable=AsyncMock, return_value=1):
            ticket = await ticket_service.create_ticket(
                CreateTicketRequest(agency_id=agency.id, service_id=service.id),
                user_id=user_id,
                org_id=org.id,
            )

    with patch("app.services.ticket_service.remove_from_queue", new_callable=AsyncMock) as mock_remove:
        await ticket_service.cancel_ticket(ticket.id, user_id, org.id)

    call_args = mock_remove.call_args
    assert call_args is not None
    # Signature : remove_from_queue(org_id, agency_id, service_id, ticket_id)
    positional = call_args.args
    assert len(positional) >= 3
    assert positional[2] == service.id, "service_id doit être le 3ème argument de remove_from_queue"


def test_callnextrequest_requires_service_id():
    """CallNextRequest sans service_id lève une ValidationError."""
    from pydantic import ValidationError
    from app.schemas.ticket import CallNextRequest

    with pytest.raises(ValidationError):
        CallNextRequest(agency_id="a-1", counter_id="c-1", counter_name="G1")


def test_callnextrequest_valid_with_service_id():
    """CallNextRequest avec service_id est valide."""
    from app.schemas.ticket import CallNextRequest

    req = CallNextRequest(
        agency_id="a-1",
        service_id="s-1",
        counter_id="c-1",
        counter_name="Guichet 1",
    )
    assert req.service_id == "s-1"
