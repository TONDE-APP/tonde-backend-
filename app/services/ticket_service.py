"""
Service Tickets — Queue Engine de TONDE.

Responsabilités :
  - Création et suivi des tickets
  - Machine à états explicite (transitions contrôlées)
  - Calcul ETA
  - Intégration Redis (file d'attente, position)
  - Isolation multi-tenant via org_id

Toute modification de ce fichier doit être analysée
avec soin : c'est le cœur du système.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.models.ticket import (
    Ticket, TicketStatus, TicketPriority,
    PRIORITY_SCORES, ALLOWED_TRANSITIONS,
)
from app.models.agency import Agency, Service
from app.core.redis import (
    add_to_queue, get_queue_position,
    get_queue_size, remove_from_queue, get_next_ticket,
)
from app.schemas.ticket import CreateTicketRequest, TicketResponse, TicketHistoryResponse

logger = logging.getLogger(__name__)

# Statuts considérés comme "actifs" — bloquent la création d'un nouveau ticket.
# Règle MVP : 1 seul ticket actif par utilisateur sur TOUTE la plateforme (DÉCISION 1).
ACTIVE_STATUSES: list[TicketStatus] = [
    TicketStatus.WAITING,
    TicketStatus.CALLED,
    TicketStatus.SERVING,
    TicketStatus.ABSENT,
    TicketStatus.TRANSFERRED,
    TicketStatus.INCOMPLETE,
]


class TicketService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Créer un nouveau ticket ───────────────────────────────────────────────
    async def create_ticket(
        self, data: CreateTicketRequest, user_id: str, org_id: str | None
        self, data: CreateTicketRequest, user_id: str, org_id: str | None = None
    ) -> TicketResponse:
        """
        Crée un ticket et l'insère dans la file d'attente Redis.

        Args:
            data: Données de création (agency_id, service_id, priority)
            user_id: ID de l'utilisateur connecté
            org_id: ID de l'organisation (isolation multi-tenant)
                    Peut être None pour les clients OTP sans affiliation
            org_id: ID de l'organisation de l'appelant si connu.
                Pour un client mobile sans org_id, l'organisation est déduite
                à partir de l'agence ciblée.

        Returns:
            TicketResponse avec numéro, position, ETA et QR token

        Raises:
            HTTPException 400: Agence fermée ou données invalides
            HTTPException 403: Agence n'appartient pas à l'org
            HTTPException 409: Ticket actif déjà existant
        """
        # Vérifier que l'agence existe
        # Pour les clients sans org (org_id=None), on récupère l'org_id depuis l'agence
        agency = await self._get_agency_for_ticket_creation(data.agency_id, org_id)
        
        # Si le client n'a pas d'org, on utilise l'org de l'agence pour le ticket
        ticket_org_id = org_id if org_id and org_id != user_id else agency.org_id
        # Résoudre l'agence et l'organisation cible.
        # Les clients mobiles n'ont pas d'org_id ; on le déduit donc de l'agence.
        agency = await self._get_agency(data.agency_id, org_id)
        if not agency.org_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "AGENCY_SCOPE_INVALID",
                    "message": "Cette agence n'est associée à aucune organisation",
                },
            )
        resolved_org_id = agency.org_id

        if not agency.is_active or not agency.is_open:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "AGENCY_CLOSED", "message": "Cette agence est fermée en ce moment"},
            )

        # Vérifier que le service existe dans cette agence
        service = await self._get_service(data.service_id, data.agency_id, ticket_org_id)
        service = await self._get_service(data.service_id, data.agency_id, resolved_org_id)

        # Règle MVP : un utilisateur ne peut avoir qu'UN SEUL ticket actif sur toute la plateforme
        existing = await self._get_active_ticket(user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "TICKET_ALREADY_ACTIVE",
                    "message": (
                        f"Vous avez déjà un ticket actif ({existing.number} — "
                        f"statut : {existing.status.value}). "
                        "Attendez qu'il soit terminé ou annulez-le avant d'en prendre un nouveau."
                    ),
                    "active_ticket_id": existing.id,
                    "active_ticket_number": existing.number,
                },
            )

        # Calculer le prochain numéro de séquence (réinitialisé chaque jour)
        sequence = await self._get_next_sequence(data.agency_id, service.ticket_prefix)
        ticket_number = f"{service.ticket_prefix}-{sequence}"

        # Résoudre la priorité
        priority = TicketPriority(data.priority) if data.priority in TicketPriority._value2member_map_ else TicketPriority.STANDARD
        priority_score = PRIORITY_SCORES[priority]

        # Persister le ticket avec l'org_id de l'agence (peut être None si agence sans org)
        ticket = Ticket(
            number=ticket_number,
            prefix=service.ticket_prefix,
            sequence=sequence,
            user_id=user_id,
            org_id=ticket_org_id,
            org_id=resolved_org_id,
            agency_id=data.agency_id,
            service_id=data.service_id,
            priority=priority,
            status=TicketStatus.WAITING,
        )
        self.db.add(ticket)
        await self.db.flush()   # obtenir ticket.id avant commit
        await self.db.commit()
        await self.db.refresh(ticket)

        # Insérer dans la file Redis (utiliser org_id pour le namespace Redis)
        redis_org_id = ticket_org_id or "public"
        position = await add_to_queue(redis_org_id, data.agency_id, ticket.id, priority_score)
        total = await get_queue_size(redis_org_id, data.agency_id)

        try:
            # Insérer dans la file Redis avant le commit DB pour garder un flux cohérent.
            position = await add_to_queue(
                resolved_org_id,
                data.agency_id,
                data.service_id,
                ticket.id,
                priority_score,
            )
            total = await get_queue_size(resolved_org_id, data.agency_id, data.service_id)

            # Calculer l'ETA
            eta = max(0, (position - 1) * agency.avg_service_minutes)
            ticket.estimated_wait_minutes = eta

            await self.db.commit()
        except Exception:
            await self.db.rollback()
            try:
                await remove_from_queue(resolved_org_id, data.agency_id, data.service_id, ticket.id)
            except Exception:
                logger.exception(
                    "Échec du nettoyage Redis après rollback create_ticket | ticket_id=%s",
                    ticket.id,
                )
            raise

        await self.db.refresh(ticket)

        logger.info(f"Ticket créé: {ticket_number} | org={ticket_org_id} | position={position} | ETA={eta}min")
        logger.info(
            f"Ticket créé: {ticket_number} | org={resolved_org_id} | position={position} | ETA={eta}min"
        )

        return TicketResponse(
            id=ticket.id,
            number=ticket.number,
            status=ticket.status.value,
            priority=ticket.priority.value,
            agency_id=ticket.agency_id,
            service_id=ticket.service_id,
            qr_token=ticket.qr_token,
            position=position,
            total_in_queue=total,
            estimated_wait_minutes=eta,
            created_at=ticket.created_at,
        )

    # ── Obtenir le statut d'un ticket ─────────────────────────────────────────
    async def get_ticket(
        self, ticket_id: str, user_id: str, org_id: str | None = None
    ) -> TicketResponse:
        """
        Retourne les informations actuelles d'un ticket.

        Sécurité : un client ne peut voir que ses propres tickets.
        org_id garantit l'isolation multi-tenant quand l'appelant est un agent.
        Pour un client mobile, on autorise l'accès par propriété du ticket.
        """
        ticket = await self._get_user_ticket(ticket_id, user_id, org_id)
        resolved_org_id = ticket.org_id

        position = await get_queue_position(resolved_org_id, ticket.agency_id, ticket.service_id, ticket.id)
        total = await get_queue_size(resolved_org_id, ticket.agency_id, ticket.service_id)

        agency_result = await self.db.execute(
            select(Agency).where(Agency.id == ticket.agency_id, Agency.org_id == resolved_org_id)
        )
        agency = agency_result.scalar_one_or_none()
        eta = max(0, (position - 1) * (agency.avg_service_minutes if agency else 5))

        return TicketResponse(
            id=ticket.id,
            number=ticket.number,
            status=ticket.status.value,
            priority=ticket.priority.value,
            agency_id=ticket.agency_id,
            service_id=ticket.service_id,
            qr_token=ticket.qr_token,
            position=position if position > 0 else 0,
            total_in_queue=total,
            estimated_wait_minutes=eta,
            created_at=ticket.created_at,
            counter_name=ticket.counter_name,
        )

    # ── Annuler un ticket ─────────────────────────────────────────────────────
    async def cancel_ticket(
        self, ticket_id: str, user_id: str, org_id: str | None = None
    ) -> dict:
        """
        Le client annule son ticket.
        Seuls les tickets WAITING peuvent être annulés par le client.
        """
        ticket = await self._get_user_ticket(ticket_id, user_id, org_id)
        resolved_org_id = ticket.org_id

        await self._transition(ticket, TicketStatus.CANCELLED)
        try:
            await remove_from_queue(resolved_org_id, ticket.agency_id, ticket.service_id, ticket.id)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        logger.info(f"Ticket annulé: {ticket.number} | user={user_id}")
        return {"success": True, "message": "Ticket annulé"}

    # ── Appeler le prochain ticket (guichetier) ───────────────────────────────
    async def call_next(
        self, agency_id: str, service_id: str, counter_id: str, counter_name: str, org_id: str
    ) -> dict:
        """
        Le guichetier appelle le prochain ticket de la file du service.

        Args:
            agency_id: ID de l'agence du guichetier
            service_id: ID du service dont appeler le prochain ticket
            counter_id: ID du guichet appelant
            counter_name: Nom affiché sur l'écran salle d'attente
            org_id: ID de l'organisation (isolation multi-tenant)

        Returns:
            Dict avec ticket_id, ticket_number, user_id pour la notif WebSocket
        """
        next_ticket_id = await get_next_ticket(org_id, agency_id, service_id)
        if not next_ticket_id:
            return {"success": False, "message": "Aucun ticket en attente"}

        ticket = await self._get_ticket_by_id(next_ticket_id, org_id)

        await self._transition(ticket, TicketStatus.CALLED)
        ticket.called_at = datetime.now(timezone.utc)
        ticket.counter_id = counter_id
        ticket.counter_name = counter_name

        await remove_from_queue(org_id, agency_id, service_id, next_ticket_id)
        await self.db.commit()
        await self.db.refresh(ticket)

        logger.info(f"Ticket appelé: {ticket.number} → guichet {counter_name} | org={org_id}")

        return {
            "success": True,
            "ticket_id": ticket.id,
            "ticket_number": ticket.number,
            "counter_name": counter_name,
            "user_id": ticket.user_id,
        }

    # ── Marquer un ticket comme en service ────────────────────────────────────
    async def start_serving(
        self, ticket_id: str, org_id: str
    ) -> dict:
        """
        Le guichetier confirme que le client est présent et le service commence.
        Transition : CALLED → SERVING
        """
        ticket = await self._get_ticket_by_id(ticket_id, org_id)
        await self._transition(ticket, TicketStatus.SERVING)
        ticket.served_at = datetime.now(timezone.utc)
        await self.db.commit()
        return {"success": True, "ticket_id": ticket_id}

    # ── Terminer un ticket ────────────────────────────────────────────────────
    async def complete_ticket(
        self, ticket_id: str, org_id: str
    ) -> dict:
        """
        Service terminé avec succès.
        Transition : SERVING → DONE
        """
        ticket = await self._get_ticket_by_id(ticket_id, org_id)
        await self._transition(ticket, TicketStatus.DONE)
        ticket.done_at = datetime.now(timezone.utc)

        # Calculer le temps réel de service
        if ticket.served_at:
            delta = ticket.done_at - ticket.served_at
            ticket.actual_wait_minutes = int(delta.total_seconds() / 60)

        await self.db.commit()
        return {"success": True, "ticket_id": ticket_id}

    # ── Marquer un ticket comme absent ───────────────────────────────────────
    async def mark_absent(self, ticket_id: str, org_id: str) -> dict:
        """
        Le client ne s'est pas présenté après timeout (3 min).
        Transition : CALLED → ABSENT
        """
        ticket = await self._get_ticket_by_id(ticket_id, org_id)
        await self._transition(ticket, TicketStatus.ABSENT)
        await self.db.commit()
        logger.info(f"Ticket absent: {ticket.number}")
        return {"success": True, "ticket_id": ticket_id}

    # ── Remettre un ticket absent en file ─────────────────────────────────────
    async def return_to_queue(
        self, ticket_id: str, user_id: str, org_id: str | None = None
    ) -> dict:
        """
        Le client absent demande à revenir dans la file.
        Transition : ABSENT → WAITING
        Le ticket revient en fin de file (priorité dégradée).
        Seul le propriétaire du ticket peut effectuer cette action.
        """
        ticket = await self._get_user_ticket(ticket_id, user_id, org_id)
        resolved_org_id = ticket.org_id
        await self._transition(ticket, TicketStatus.WAITING)

        # Remettre en file avec priorité standard (pénalité)
        priority_score = PRIORITY_SCORES[TicketPriority.STANDARD]
        try:
            await add_to_queue(resolved_org_id, ticket.agency_id, ticket.service_id, ticket.id, priority_score)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return {"success": True, "ticket_id": ticket_id}

    # ── Historique paginé ─────────────────────────────────────────────────────
    async def get_history(
        self, user_id: str, page: int = 1
    ) -> TicketHistoryResponse:
        """
        Retourne l'historique paginé des tickets d'un utilisateur.

        Args:
            user_id: ID de l'utilisateur
            page: Numéro de page (commence à 1)

        Returns:
            TicketHistoryResponse avec items, total, page, has_next
        """
        page_size = 20
        offset = (page - 1) * page_size

        # Compter le total
        count_result = await self.db.execute(
            select(func.count(Ticket.id)).where(Ticket.user_id == user_id)
        )
        total = count_result.scalar() or 0

        # Récupérer la page
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.user_id == user_id)
            .order_by(Ticket.created_at.desc())
            .limit(page_size)
            .offset(offset)
        )
        tickets = result.scalars().all()

        items = [
            TicketResponse(
                id=t.id,
                number=t.number,
                status=t.status.value,
                priority=t.priority.value,
                agency_id=t.agency_id,
                service_id=t.service_id,
                qr_token=t.qr_token,
                position=0,
                total_in_queue=0,
                estimated_wait_minutes=t.estimated_wait_minutes,
                created_at=t.created_at,
                counter_name=t.counter_name,
            )
            for t in tickets
        ]

        return TicketHistoryResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(offset + page_size) < total,
        )

    # ── Machine à états ───────────────────────────────────────────────────────
    async def _transition(
        self, ticket: Ticket, new_status: TicketStatus
    ) -> None:
        """
        Applique une transition d'état sur un ticket.
        Vérifie que la transition est autorisée selon ALLOWED_TRANSITIONS.

        Raises:
            HTTPException 400: Si la transition est interdite
        """
        allowed = ALLOWED_TRANSITIONS.get(ticket.status, [])
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_TRANSITION",
                    "message": (
                        f"Transition interdite : {ticket.status.value} → {new_status.value}. "
                        f"Transitions autorisées depuis {ticket.status.value} : "
                        f"{[s.value for s in allowed] or 'aucune (état terminal)'}"
                    ),
                },
            )
        ticket.status = new_status

    # ── Helpers privés ────────────────────────────────────────────────────────
    async def _get_agency_for_ticket_creation(
        self, agency_id: str, user_org_id: str | None
    ) -> Agency:
        """
        Récupère une agence pour la création de ticket.
        
        Différence avec _get_agency : permet aux clients sans org (user_org_id=None ou =user_id)
        de créer des tickets dans les agences publiques (org_id=NULL) ou affiliées.
        """
        # Si l'utilisateur a une org ou si c'est un agent, on vérifie l'appartenance
        if user_org_id and user_org_id != "":
            result = await self.db.execute(
                select(Agency).where(
                    Agency.id == agency_id,
                    Agency.org_id == user_org_id,
                )
            )
            agency = result.scalar_one_or_none()
            if agency:
                return agency
        
        # Sinon, pour les clients sans org, on cherche une agence existante
        # (agence publique ou agence avec une org)
        result = await self.db.execute(
            select(Agency).where(Agency.id == agency_id)
        )
        agency = result.scalar_one_or_none()
        if not agency:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "AGENCY_NOT_FOUND", "message": "Agence introuvable"},
            )
        return agency

    async def _get_agency(self, agency_id: str, org_id: str) -> Agency:
        """Récupère une agence en vérifiant son appartenance à l'organisation."""
        result = await self.db.execute(
            select(Agency).where(
                Agency.id == agency_id,
                Agency.org_id == org_id,
            )
        )
    async def _get_agency(self, agency_id: str, org_id: str | None = None) -> Agency:
        """
        Récupère une agence.

        Si org_id est fourni, l'agence doit appartenir à cette organisation.
        Sinon, l'agence est résolue globalement et son org_id sera utilisé ensuite.
        """
        query = select(Agency).where(Agency.id == agency_id)
        if org_id is not None:
            query = query.where(Agency.org_id == org_id)

        result = await self.db.execute(query)
        agency = result.scalar_one_or_none()
        if not agency:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "AGENCY_NOT_FOUND", "message": "Agence introuvable"},
            )
        return agency

    async def _get_service(
        self, service_id: str, agency_id: str, org_id: str | None
    ) -> Service:
        """Récupère un service en vérifiant son appartenance à l'agence et l'org."""
        query = select(Service).where(
            Service.id == service_id,
            Service.agency_id == agency_id,
        )
        # Si org_id est fourni, vérifier qu'il correspond
        if org_id:
            query = query.where(Service.org_id == org_id)
        
        result = await self.db.execute(query)
        service = result.scalar_one_or_none()
        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SERVICE_NOT_FOUND", "message": "Service introuvable"},
            )
        return service

    async def _get_ticket_by_id(self, ticket_id: str, org_id: str | None = None) -> Ticket:
        """
        Récupère un ticket.

        Si org_id est fourni, le ticket doit appartenir à cette organisation.
        Sinon, le ticket est résolu globalement puis contrôlé par propriété utilisateur.
        """
        query = select(Ticket).where(Ticket.id == ticket_id)
        if org_id is not None:
            query = query.where(Ticket.org_id == org_id)

        result = await self.db.execute(query)
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "TICKET_NOT_FOUND", "message": "Ticket introuvable"},
            )
        return ticket

    async def _get_user_ticket(
        self, ticket_id: str, user_id: str, org_id: str | None = None
    ) -> Ticket:
        """Retourne un ticket appartenant à l'utilisateur connecté."""
        ticket = await self._get_ticket_by_id(ticket_id, org_id)
        if ticket.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Accès non autorisé à ce ticket"},
            )
        return ticket

    async def _get_active_ticket(
        self, user_id: str
    ) -> "Ticket | None":
        """
        Vérifie si l'utilisateur possède un ticket actif sur toute la plateforme.

        Règle MVP (DÉCISION 1) : vérification globale sans filtre sur agency_id.
        Les statuts bloquants sont définis par la constante ACTIVE_STATUSES.

        Args:
            user_id: ID de l'utilisateur à vérifier.

        Returns:
            Le ticket actif trouvé, ou None si l'utilisateur est libre.
        """
        result = await self.db.execute(
            select(Ticket)
            .where(
                Ticket.user_id == user_id,
                Ticket.status.in_(ACTIVE_STATUSES),
            )
            .order_by(Ticket.created_at.desc())
        )
        return result.scalars().first()

    async def _get_next_sequence(self, agency_id: str, prefix: str) -> int:
        """
        Génère le prochain numéro de séquence pour le jour en cours.
        La séquence repart à 1 chaque jour à minuit UTC.
        """
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = await self.db.execute(
            select(func.count(Ticket.id)).where(
                Ticket.agency_id == agency_id,
                Ticket.prefix == prefix,
                Ticket.created_at >= today_start,
            )
        )
        count = result.scalar() or 0
        return count + 1
