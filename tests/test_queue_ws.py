"""
Tests unitaires — QueueWebSocketManager (Redis Pub/Sub listener)

TASK-05 : vérifie que start_redis_listener() dispatche correctement
les événements, gère les messages malformés et se reconnecte après erreur.
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.websocket.queue_ws import QueueWebSocketManager
from app.websocket.events import EventType


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _aiter(items):
    """Générateur async pour simuler pubsub.listen() avec une liste de messages."""
    for item in items:
        yield item


def _make_pmessage(data: dict) -> dict:
    """Construit un message Redis de type pmessage."""
    return {"type": "pmessage", "data": json.dumps(data), "channel": "tonde:events:org-1"}


def _make_subscribe_confirmation() -> dict:
    """Message de confirmation de souscription — doit être ignoré par le listener."""
    return {"type": "psubscribe", "data": 1, "channel": "tonde:events:*"}


def _make_mock_pubsub(messages: list) -> AsyncMock:
    """Construit un mock pubsub qui retourne les messages fournis puis se termine."""
    mock_pubsub = AsyncMock()
    mock_pubsub.__aenter__ = AsyncMock(return_value=mock_pubsub)
    mock_pubsub.__aexit__ = AsyncMock(return_value=None)
    mock_pubsub.psubscribe = AsyncMock()
    mock_pubsub.listen = MagicMock(return_value=_aiter(messages))
    return mock_pubsub


async def _run_listener_with_messages(ws_manager, messages: list) -> None:
    """Lance le listener, le laisse traiter les messages, puis l'annule."""
    mock_pubsub = _make_mock_pubsub(messages)
    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    # get_redis est importé localement dans start_redis_listener → patcher à la source
    with patch("app.core.redis.get_redis", new_callable=AsyncMock, return_value=mock_redis):
        task = asyncio.create_task(ws_manager.start_redis_listener())
        await asyncio.sleep(0.05)  # laisser le listener traiter les messages
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listener_dispatches_your_turn_event():
    """Un événement 'your_turn' est dispatché vers send_to_ticket()."""
    ws_manager = QueueWebSocketManager()
    event = {
        "type": EventType.YOUR_TURN,
        "ticket_id": "ticket-abc",
        "ticket_number": "A-5",
        "counter_name": "Guichet 1",
        "message": "Présentez-vous au Guichet 1",
    }

    with patch.object(ws_manager, "_dispatch_event", new_callable=AsyncMock) as mock_dispatch:
        await _run_listener_with_messages(ws_manager, [_make_pmessage(event)])

    mock_dispatch.assert_called_once()
    dispatched = mock_dispatch.call_args.args[0]
    assert dispatched["type"] == EventType.YOUR_TURN
    assert dispatched["ticket_id"] == "ticket-abc"


@pytest.mark.asyncio
async def test_listener_dispatches_ticket_called_event():
    """Un événement 'ticket_called' est dispatché vers broadcast_to_agency()."""
    ws_manager = QueueWebSocketManager()
    event = {
        "type": EventType.TICKET_CALLED,
        "called_number": "A-5",
        "counter_name": "Guichet 1",
        "agency_id": "agency-xyz",
    }

    with patch.object(ws_manager, "_dispatch_event", new_callable=AsyncMock) as mock_dispatch:
        await _run_listener_with_messages(ws_manager, [_make_pmessage(event)])

    mock_dispatch.assert_called_once()
    dispatched = mock_dispatch.call_args.args[0]
    assert dispatched["type"] == EventType.TICKET_CALLED
    assert dispatched["agency_id"] == "agency-xyz"


@pytest.mark.asyncio
async def test_listener_skips_subscribe_confirmation_messages():
    """Les messages de confirmation psubscribe/subscribe sont ignorés silencieusement."""
    ws_manager = QueueWebSocketManager()

    with patch.object(ws_manager, "_dispatch_event", new_callable=AsyncMock) as mock_dispatch:
        await _run_listener_with_messages(
            ws_manager,
            [_make_subscribe_confirmation()]  # type "psubscribe" → doit être ignoré
        )

    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_listener_handles_invalid_json_gracefully():
    """Un message avec data non-JSON ne fait pas crasher la boucle."""
    ws_manager = QueueWebSocketManager()

    bad_message = {"type": "pmessage", "data": "not-valid-json{{{", "channel": "tonde:events:org-1"}
    valid_event = {"type": EventType.QUEUE_UPDATE, "ticket_id": "t-1"}

    with patch.object(ws_manager, "_dispatch_event", new_callable=AsyncMock) as mock_dispatch:
        await _run_listener_with_messages(
            ws_manager,
            [bad_message, _make_pmessage(valid_event)]
        )

    # Le message valide APRÈS le message malformé doit quand même être dispatché
    mock_dispatch.assert_called_once()
    dispatched = mock_dispatch.call_args.args[0]
    assert dispatched["ticket_id"] == "t-1"


@pytest.mark.asyncio
async def test_listener_handles_dispatch_exception_gracefully():
    """Une exception dans _dispatch_event ne casse pas la boucle du listener."""
    ws_manager = QueueWebSocketManager()

    event1 = {"type": EventType.YOUR_TURN, "ticket_id": "t-fail"}
    event2 = {"type": EventType.QUEUE_UPDATE, "ticket_id": "t-ok"}

    call_count = 0

    async def dispatch_side_effect(event):
        nonlocal call_count
        call_count += 1
        if event.get("ticket_id") == "t-fail":
            raise RuntimeError("erreur dispatch simulée")

    with patch.object(ws_manager, "_dispatch_event", side_effect=dispatch_side_effect):
        await _run_listener_with_messages(
            ws_manager,
            [_make_pmessage(event1), _make_pmessage(event2)]
        )

    # Les deux messages ont été tentés — la boucle n'a pas crashé sur la 1ère erreur
    assert call_count == 2


@pytest.mark.asyncio
async def test_listener_skips_empty_data_messages():
    """Un message avec data vide ou None est ignoré sans exception."""
    ws_manager = QueueWebSocketManager()

    empty_message = {"type": "pmessage", "data": None, "channel": "tonde:events:org-1"}

    with patch.object(ws_manager, "_dispatch_event", new_callable=AsyncMock) as mock_dispatch:
        await _run_listener_with_messages(ws_manager, [empty_message])

    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_listener_reconnects_after_redis_exception():
    """Après une exception Redis, le listener attend 5s puis tente de se reconnecter."""
    ws_manager = QueueWebSocketManager()

    call_count = 0

    async def flaky_get_redis():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("Redis indisponible")
        # 2ème appel : retourner un mock qui produit 0 message puis stoppe
        mock_redis = AsyncMock()
        mock_pubsub = _make_mock_pubsub([])
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
        return mock_redis

    with patch("app.core.redis.get_redis", side_effect=flaky_get_redis):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            task = asyncio.create_task(ws_manager.start_redis_listener())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # get_redis a été appelé au moins 2 fois (1ère erreur + reconnexion)
    assert call_count >= 2
    # asyncio.sleep(5) a bien été appelé pour le backoff
    mock_sleep.assert_called_with(5)
