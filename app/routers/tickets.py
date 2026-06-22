"""
Router Tickets — /api/v1/tickets/...

Tous les endpoints REST sont protégés par JWT.
Les endpoints WebSocket utilisent l'auth par query param.
Le guichetier doit avoir le rôle AGENT minimum.
"""
import logging
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_agent, get_ws_user
from app.core.middlewares import limiter
from app.models.user import User
from app.schemas.ticket import CreateTicketRequest, CallNextRequest
from app.services.ticket_service import TicketService
from app.websocket.queue_ws import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_org_id(current_user: User) -> str:
    """
    Retourne l'org_id de l'utilisateur.
    Pour les clients sans org, utilise l'user_id comme namespace
    (sera revu quand les clients seront liés à une org via le ticket).
    """
    return current_user.org_id or current_user.id


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.post("", summary="Créer un nouveau ticket")
async def create_ticket(
    body: CreateTicketRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Le mobile appelle cet endpoint pour prendre un ticket.
    Retourne numéro, position dans la file et temps estimé.
    """
    service = TicketService(db)
    return await service.create_ticket(body, current_user.id, _get_org_id(current_user))


@router.get("/history", summary="Historique des tickets")
async def get_history(
    page: int = Query(default=1, ge=1, description="Numéro de page"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne l'historique paginé des tickets de l'utilisateur connecté.
    Inclut total et has_next pour la pagination mobile.
    """
    service = TicketService(db)
    return await service.get_history(current_user.id, page)


@router.get("/{ticket_id}", summary="Détail d'un ticket")
async def get_ticket(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)
    return await service.get_ticket(ticket_id, current_user.id, _get_org_id(current_user))


@router.delete("/{ticket_id}", summary="Annuler un ticket")
async def cancel_ticket(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = TicketService(db)
    return await service.cancel_ticket(ticket_id, current_user.id, _get_org_id(current_user))


@router.post("/counter/call-next", summary="Guichetier appelle le prochain ticket")
async def call_next(
    body: CallNextRequest,
    current_user: User = Depends(get_current_agent),  # ← rôle AGENT minimum
    db: AsyncSession = Depends(get_db),
):
    """
    Le guichetier appelle le prochain ticket de la file.
    Nécessite le rôle AGENT, SUPERVISOR, ADMIN_AGENCY, ADMIN_ORG ou SUPER_ADMIN.
    Notifie le client en temps réel via WebSocket.
    """
    if not current_user.org_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_ORG", "message": "Cet agent n'est pas associé à une organisation"},
        )

    service = TicketService(db)
    result = await service.call_next(
        agency_id=body.agency_id,
        service_id=body.service_id,
        counter_id=body.counter_id,
        counter_name=body.counter_name,
        org_id=current_user.org_id,
    )

    # Notifier le client en temps réel si le ticket a été trouvé
    if result.get("success"):
        await ws_manager.notify_your_turn(
            ticket_id=result["ticket_id"],
            ticket_number=result["ticket_number"],
            counter_name=body.counter_name,
        )
        await ws_manager.broadcast_to_agency(body.agency_id, {
            "type": "queue_called",
            "called_number": result["ticket_number"],
            "counter_name": body.counter_name,
        })

    return result


@router.post("/{ticket_id}/serving", summary="Guichetier confirme le service")
async def start_serving(
    ticket_id: str,
    current_user: User = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Transition CALLED → SERVING. Le client est physiquement au guichet."""
    service = TicketService(db)
    return await service.start_serving(ticket_id, current_user.org_id or "")


@router.post("/{ticket_id}/done", summary="Guichetier termine le service")
async def complete_ticket(
    ticket_id: str,
    current_user: User = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Transition SERVING → DONE. Service terminé avec succès."""
    service = TicketService(db)
    return await service.complete_ticket(ticket_id, current_user.org_id or "")


@router.post("/{ticket_id}/absent", summary="Marquer un client absent")
async def mark_absent(
    ticket_id: str,
    current_user: User = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Transition CALLED → ABSENT. Le client ne s'est pas présenté."""
    service = TicketService(db)
    return await service.mark_absent(ticket_id, current_user.org_id or "")


@router.post("/{ticket_id}/return", summary="Client absent revient en file")
async def return_to_queue(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transition ABSENT → WAITING. Le client redemande sa place."""
    service = TicketService(db)
    return await service.return_to_queue(ticket_id, _get_org_id(current_user))


# ── WebSocket endpoints ───────────────────────────────────────────────────────

@router.websocket("/ws/queue/{ticket_id}")
@limiter.limit("10/minute")
async def websocket_queue(
    websocket: WebSocket,
    ticket_id: str,
    agency_id: str = Query(..., description="ID de l'agence"),
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket pour le suivi temps réel d'un ticket côté client mobile.

    Le client se connecte après avoir pris un ticket.
    Il reçoit les mises à jour de position automatiquement.

    URL Flutter :
        ws://api.tonde.app/api/v1/tickets/ws/queue/$ticketId
        ?agency_id=$agencyId&token=$accessToken
    """
    # Authentifier via le token JWT en query param
    user_id = None
    try:
        from app.core.security import verify_token
        user_id = verify_token(token, token_type="access")
    except Exception:
        pass

    if not user_id:
        await websocket.close(code=4001, reason="Token invalide")
        return

    await ws_manager.connect_client(websocket, ticket_id, agency_id)
    logger.info(f"WS connecté — ticket={ticket_id} | user={user_id}")

    try:
        await websocket.send_text('{"type": "connected", "message": "Suivi activé"}')

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type": "pong"}')

    except WebSocketDisconnect:
        ws_manager.disconnect_client(ticket_id, agency_id)
        logger.info(f"WS déconnecté — ticket={ticket_id}")


@router.websocket("/ws/counter/{counter_id}")
@limiter.limit("10/minute")
async def websocket_counter(
    websocket: WebSocket,
    counter_id: str,
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket pour le guichetier desktop.
    Reçoit les notifications en temps réel (nouveau ticket, annulation, etc.).
    Nécessite un token valide avec rôle AGENT minimum.
    """
    # Authentifier et vérifier le rôle
    try:
        from app.core.security import verify_token
        from app.models.user import UserRole
        from sqlalchemy import select
        from app.models.user import User as UserModel

        user_id = verify_token(token, token_type="access")
        if not user_id:
            raise ValueError("Token invalide")

        async with db as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            user = result.scalar_one_or_none()

        if not user or user.role == UserRole.CLIENT:
            await websocket.close(code=4003, reason="Accès réservé aux agents")
            return

    except Exception as e:
        logger.warning(f"WS counter auth échoué: {e}")
        await websocket.close(code=4001, reason="Token invalide")
        return

    await ws_manager.connect_counter(websocket, counter_id)
    logger.info(f"WS guichet connecté — counter={counter_id} | agent={user_id}")

    try:
        await websocket.send_text('{"type": "connected", "message": "Guichet connecté"}')
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type": "pong"}')
    except WebSocketDisconnect:
        ws_manager.counter_connections.pop(counter_id, None)
        logger.info(f"WS guichet déconnecté — counter={counter_id}")
