"""
WebSocket Manager — Gestion des connexions temps réel TONDE.

Architecture :
  Queue Engine publie un événement
       ↓
  Redis Pub/Sub (channel : tonde:events:{org_id})
       ↓
  QueueWebSocketManager.redis_listener() (background task)
       ↓
  Clients connectés (mobile, desktop)

Cette architecture permet le déploiement multi-instance :
un événement publié sur le serveur A est reçu par les clients
connectés sur le serveur B via Redis.

Objectifs de performance :
  P50 < 100ms | P99 < 300ms
"""
import json
import asyncio
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect

from app.websocket.events import (
    EventType, YourTurnEvent, TicketCalledEvent,
    make_connected_event, make_pong_event,
)

logger = logging.getLogger(__name__)

# Canal Redis Pub/Sub pour les événements TONDE
REDIS_EVENTS_CHANNEL = "tonde:events:{org_id}"


class QueueWebSocketManager:
    """
    Gère toutes les connexions WebSocket actives.

    Indexation des connexions :
      connections_by_ticket  : ticket_id  → WebSocket  (client mobile)
      connections_by_agency  : agency_id  → Set[WebSocket] (broadcast salle)
      counter_connections    : counter_id → WebSocket  (guichetier desktop)
    """

    def __init__(self):
        # Mobile client → suivi de son ticket
        self.connections_by_ticket: Dict[str, WebSocket] = {}
        # Tous les clients d'une agence → broadcast salle d'attente
        self.connections_by_agency: Dict[str, Set[WebSocket]] = {}
        # Guichetiers desktop
        self.counter_connections: Dict[str, WebSocket] = {}

    # ── Connexions ────────────────────────────────────────────────────────────

    async def connect_client(
        self, websocket: WebSocket, ticket_id: str, agency_id: str
    ) -> None:
        """
        Enregistre la connexion d'un client mobile qui suit son ticket.

        Args:
            websocket: La connexion WebSocket acceptée
            ticket_id: UUID du ticket suivi
            agency_id: UUID de l'agence (pour le broadcast)
        """
        await websocket.accept()
        self.connections_by_ticket[ticket_id] = websocket

        if agency_id not in self.connections_by_agency:
            self.connections_by_agency[agency_id] = set()
        self.connections_by_agency[agency_id].add(websocket)

        logger.info(f"WS client connecté — ticket={ticket_id} | agency={agency_id}")

    async def connect_counter(
        self, websocket: WebSocket, counter_id: str
    ) -> None:
        """Enregistre la connexion d'un guichetier desktop."""
        await websocket.accept()
        self.counter_connections[counter_id] = websocket
        logger.info(f"WS guichet connecté — counter={counter_id}")

    def disconnect_client(self, ticket_id: str, agency_id: str) -> None:
        """Nettoie la connexion après déconnexion d'un client."""
        self.connections_by_ticket.pop(ticket_id, None)
        if agency_id in self.connections_by_agency:
            self.connections_by_agency[agency_id] = {
                ws for ws in self.connections_by_agency[agency_id]
                if not self._is_disconnected(ws)
            }
        logger.info(f"WS client déconnecté — ticket={ticket_id}")

    # ── Envoi ciblé ───────────────────────────────────────────────────────────

    async def send_to_ticket(self, ticket_id: str, data: dict) -> None:
        """
        Envoie un message au mobile qui suit ce ticket précis.
        Nettoie la connexion si elle est morte.
        """
        websocket = self.connections_by_ticket.get(ticket_id)
        if websocket:
            try:
                await websocket.send_text(json.dumps(data))
            except Exception as e:
                logger.warning(f"Échec envoi WS ticket={ticket_id}: {e}")
                self.connections_by_ticket.pop(ticket_id, None)

    async def send_to_counter(self, counter_id: str, data: dict) -> None:
        """Envoie un message à un guichetier spécifique."""
        websocket = self.counter_connections.get(counter_id)
        if websocket:
            try:
                await websocket.send_text(json.dumps(data))
            except Exception as e:
                logger.warning(f"Échec envoi WS counter={counter_id}: {e}")
                self.counter_connections.pop(counter_id, None)

    # ── Broadcast ─────────────────────────────────────────────────────────────

    async def broadcast_to_agency(self, agency_id: str, data: dict) -> None:
        """
        Diffuse un message à TOUS les clients connectés dans cette agence.
        Utilisé quand le guichetier appelle un numéro (toute la salle voit).
        Nettoie automatiquement les connexions mortes.
        """
        if agency_id not in self.connections_by_agency:
            return

        message = json.dumps(data)
        disconnected: Set[WebSocket] = set()

        for websocket in self.connections_by_agency[agency_id]:
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected.add(websocket)

        # Nettoyer les connexions mortes
        if disconnected:
            self.connections_by_agency[agency_id] -= disconnected
            logger.debug(f"Nettoyage {len(disconnected)} connexions mortes — agency={agency_id}")

    # ── Événements métier ─────────────────────────────────────────────────────

    async def notify_your_turn(
        self, ticket_id: str, ticket_number: str, counter_name: str
    ) -> None:
        """
        Notifie le client que c'est son tour.
        Le téléphone affiche l'alerte et vibre.
        """
        event = YourTurnEvent(
            ticket_id=ticket_id,
            ticket_number=ticket_number,
            counter_name=counter_name,
            message=f"Présentez-vous au {counter_name}",
        )
        await self.send_to_ticket(ticket_id, event.model_dump())

    async def send_queue_update(
        self,
        ticket_id: str,
        ticket_number: str,
        current_called_number: str,
        position: int,
        total: int,
        eta_minutes: int,
    ) -> None:
        """Envoie la mise à jour de position à un client spécifique."""
        await self.send_to_ticket(ticket_id, {
            "type": EventType.QUEUE_UPDATE,
            "ticket_id": ticket_id,
            "ticket_number": ticket_number,
            "current_called_number": current_called_number,
            "position": position,
            "total_in_queue": total,
            "estimated_wait_minutes": eta_minutes,
        })

    # ── Redis Pub/Sub ─────────────────────────────────────────────────────────

    async def start_redis_listener(self, org_id: str) -> None:
        """
        Démarre l'écoute des événements Redis Pub/Sub pour une organisation.

        Cette méthode doit être lancée en background task au démarrage.
        Elle reçoit les événements publiés par le Queue Engine et les
        diffuse aux clients WebSocket connectés.

        TODO Sprint 1 : intégrer dans le lifespan de main.py
        """
        from app.core.redis import get_redis
        r = await get_redis()
        channel = REDIS_EVENTS_CHANNEL.format(org_id=org_id)

        async with r.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            logger.info(f"Redis Pub/Sub — écoute sur {channel}")

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    event = json.loads(message["data"])
                    await self._dispatch_event(event)
                except Exception as e:
                    logger.error(f"Erreur dispatch événement Redis: {e}", exc_info=True)

    async def _dispatch_event(self, event: dict) -> None:
        """
        Route un événement Redis vers les bons clients WebSocket.
        Appelé par start_redis_listener() pour chaque message reçu.
        """
        event_type = event.get("type")

        if event_type == EventType.YOUR_TURN:
            await self.send_to_ticket(event["ticket_id"], event)

        elif event_type == EventType.TICKET_CALLED:
            await self.broadcast_to_agency(event["agency_id"], event)

        elif event_type == EventType.QUEUE_UPDATE:
            await self.send_to_ticket(event["ticket_id"], event)

        elif event_type == EventType.BROADCAST_MESSAGE:
            await self.broadcast_to_agency(event["agency_id"], event)

        else:
            logger.debug(f"Événement non routé : {event_type}")

    async def publish_event(self, org_id: str, event: dict) -> None:
        """
        Publie un événement dans le canal Redis de l'organisation.
        Appelé par les services métier (Queue Engine) pour déclencher
        une diffusion WebSocket de façon découplée.

        Args:
            org_id: Identifiant de l'organisation
            event: Dict représentant l'événement (doit contenir 'type')
        """
        from app.core.redis import get_redis
        r = await get_redis()
        channel = REDIS_EVENTS_CHANNEL.format(org_id=org_id)
        await r.publish(channel, json.dumps(event))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_disconnected(websocket: WebSocket) -> bool:
        """Vérifie si une connexion WebSocket est fermée."""
        try:
            return websocket.client_state.name in ("DISCONNECTED", "CLOSED")
        except Exception:
            return True

    def get_stats(self) -> dict:
        """Retourne les statistiques de connexion (pour le /health)."""
        return {
            "clients_by_ticket": len(self.connections_by_ticket),
            "agencies_tracked": len(self.connections_by_agency),
            "counter_connections": len(self.counter_connections),
            "total_clients": sum(
                len(ws_set) for ws_set in self.connections_by_agency.values()
            ),
        }


# ── Instance globale unique ───────────────────────────────────────────────────
ws_manager = QueueWebSocketManager()
