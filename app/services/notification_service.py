"""
NotificationService — Envoi de notifications multi-canal.

Channels supportés :
  - SMS via Africa's Talking
  - FCM via Firebase Cloud Messaging (httpx, sans SDK)
  - In-app (persistance uniquement)

Toutes les notifications sont persistées dans la table 'notifications'
pour l'audit trail et les analytics (DÉCISION 9 — collecte de données).

Rules Engine intégré :
  - Alerte si temps d'attente > 30 minutes
  - Notification "votre tour" lors de l'appel du ticket
  - Notification "service terminé" après DONE

En développement (ENVIRONMENT=development) :
  - Aucun SMS ni FCM réel n'est envoyé
  - Tout est loggué uniquement
"""
import logging
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import Notification, NotificationChannel, NotificationStatus
from app.models.ticket import Ticket
from app.models.user import User

logger = logging.getLogger(__name__)

# URL de l'API Firebase Legacy HTTP (FCM)
_FCM_URL = "https://fcm.googleapis.com/fcm/send"


class NotificationService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── SMS via Africa's Talking ──────────────────────────────────────────────
    async def send_sms(
        self,
        phone: str,
        message: str,
        org_id: str,
        user_id: str,
        ticket_id: str | None = None,
    ) -> bool:
        """
        Envoie un SMS via Africa's Talking et persiste le log.

        En développement, aucun SMS n'est envoyé — le message est loggué.
        En production, un échec d'envoi ne bloque jamais l'opération principale ;
        le statut FAILED est persisté pour un retry ultérieur.

        Args:
            phone: Numéro de téléphone du destinataire (format international)
            message: Contenu du SMS (max 160 caractères recommandé)
            org_id: ID de l'organisation (isolation multi-tenant)
            user_id: ID de l'utilisateur destinataire
            ticket_id: ID du ticket associé (optionnel)

        Returns:
            True si envoyé avec succès, False en cas d'échec
        """
        notification = Notification(
            org_id=org_id,
            user_id=user_id,
            ticket_id=ticket_id,
            channel=NotificationChannel.SMS,
            body=message,
            status=NotificationStatus.PENDING,
        )
        self.db.add(notification)
        await self.db.flush()  # obtenir l'ID avant commit

        success = False

        if settings.ENVIRONMENT == "development":
            logger.debug(f"[DEV] SMS simulé → {phone}: {message}")
            success = True
        else:
            try:
                import africastalking
                africastalking.initialize(
                    settings.AFRICAS_TALKING_USERNAME,
                    settings.AFRICAS_TALKING_API_KEY,
                )
                sms = africastalking.SMS
                sms.send(message, [phone], sender_id=settings.AFRICAS_TALKING_SENDER_ID)
                success = True
                logger.info(f"SMS envoyé → {phone}")
            except Exception as e:
                logger.error(f"Échec envoi SMS → {phone}: {e}", exc_info=True)
                notification.error_message = str(e)[:500]

        notification.status = NotificationStatus.SENT if success else NotificationStatus.FAILED
        notification.sent_at = datetime.now(timezone.utc) if success else None
        await self.db.commit()

        return success

    # ── Push Notification via Firebase FCM ───────────────────────────────────
    async def send_fcm(
        self,
        fcm_token: str,
        title: str,
        body: str,
        org_id: str,
        user_id: str,
        data: dict | None = None,
        ticket_id: str | None = None,
    ) -> bool:
        """
        Envoie une push notification via Firebase FCM (httpx, sans SDK).

        En développement, aucune requête FCM n'est faite — loggué uniquement.
        Si FIREBASE_SERVER_KEY est absent, l'envoi est ignoré silencieusement.

        Args:
            fcm_token: Token FCM du device mobile de l'utilisateur
            title: Titre de la notification push
            body: Corps de la notification push
            org_id: ID de l'organisation (isolation multi-tenant)
            user_id: ID de l'utilisateur destinataire
            data: Données additionnelles (payload JSON pour l'app mobile)
            ticket_id: ID du ticket associé (optionnel)

        Returns:
            True si envoyé avec succès, False en cas d'échec ou FCM non configuré
        """
        notification = Notification(
            org_id=org_id,
            user_id=user_id,
            ticket_id=ticket_id,
            channel=NotificationChannel.FCM,
            title=title,
            body=body,
            status=NotificationStatus.PENDING,
        )
        self.db.add(notification)
        await self.db.flush()

        success = False

        if settings.ENVIRONMENT == "development":
            logger.debug(f"[DEV] FCM simulé → user={user_id}: [{title}] {body}")
            success = True
        elif not settings.FIREBASE_SERVER_KEY:
            logger.warning("FCM ignoré — FIREBASE_SERVER_KEY non configuré")
            notification.status = NotificationStatus.FAILED
            notification.error_message = "FIREBASE_SERVER_KEY manquant"
            await self.db.commit()
            return False
        else:
            try:
                payload = {
                    "to": fcm_token,
                    "notification": {"title": title, "body": body},
                    "data": data or {},
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        _FCM_URL,
                        headers={
                            "Authorization": f"key={settings.FIREBASE_SERVER_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                if response.status_code == 200:
                    success = True
                    logger.info(f"FCM envoyé → user={user_id}")
                else:
                    error_msg = f"FCM HTTP {response.status_code}: {response.text[:200]}"
                    logger.error(error_msg)
                    notification.error_message = error_msg
            except Exception as e:
                logger.error(f"Échec envoi FCM → user={user_id}: {e}", exc_info=True)
                notification.error_message = str(e)[:500]

        notification.status = NotificationStatus.SENT if success else NotificationStatus.FAILED
        notification.sent_at = datetime.now(timezone.utc) if success else None
        await self.db.commit()

        return success

    # ── Notification in-app ───────────────────────────────────────────────────
    async def save_in_app(
        self,
        title: str,
        body: str,
        org_id: str,
        user_id: str,
        ticket_id: str | None = None,
    ) -> Notification:
        """
        Persiste une notification in-app sans envoi externe.

        Utilisé pour les notifications consultables dans l'app mobile
        (historique, centre de notifications).

        Args:
            title: Titre de la notification
            body: Corps du message
            org_id: ID de l'organisation
            user_id: ID de l'utilisateur destinataire
            ticket_id: ID du ticket associé (optionnel)

        Returns:
            L'objet Notification persisté
        """
        notification = Notification(
            org_id=org_id,
            user_id=user_id,
            ticket_id=ticket_id,
            channel=NotificationChannel.IN_APP,
            title=title,
            body=body,
            status=NotificationStatus.SENT,
            sent_at=datetime.now(timezone.utc),
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    # ── Triggers métier ───────────────────────────────────────────────────────
    async def notify_ticket_called(self, ticket: Ticket, user: User) -> None:
        """
        Déclenché quand un ticket passe à l'état CALLED.
        Envoie SMS au client et FCM si un token est disponible.

        Trigger : TicketService.call_next() → après transition WAITING → CALLED

        Args:
            ticket: Le ticket qui vient d'être appelé
            user: L'utilisateur propriétaire du ticket
        """
        counter_name = ticket.counter_name or "votre guichet"
        sms_message = (
            f"TONDE: Votre numéro {ticket.number} est appelé. "
            f"Présentez-vous au {counter_name}. "
            f"Vous avez 3 minutes."
        )

        org_id = ticket.org_id
        user_id = user.id
        ticket_id = ticket.id

        # SMS si numéro disponible
        if user.phone:
            await self.send_sms(
                phone=user.phone,
                message=sms_message,
                org_id=org_id,
                user_id=user_id,
                ticket_id=ticket_id,
            )

        # FCM si token disponible
        if user.fcm_token:
            await self.send_fcm(
                fcm_token=user.fcm_token,
                title=f"C'est votre tour — {ticket.number}",
                body=f"Présentez-vous au {counter_name}",
                org_id=org_id,
                user_id=user_id,
                data={
                    "type": "YOUR_TURN",
                    "ticket_id": ticket_id,
                    "ticket_number": ticket.number,
                    "counter_name": counter_name,
                },
                ticket_id=ticket_id,
            )

        # In-app toujours
        await self.save_in_app(
            title=f"C'est votre tour — {ticket.number}",
            body=f"Présentez-vous au {counter_name}. Vous avez 3 minutes.",
            org_id=org_id,
            user_id=user_id,
            ticket_id=ticket_id,
        )

    async def notify_ticket_done(self, ticket: Ticket, user: User) -> None:
        """
        Déclenché quand un ticket passe à l'état DONE.
        Persiste une notification in-app de confirmation de service.

        Trigger : TicketService.complete_ticket() → après transition SERVING → DONE

        Args:
            ticket: Le ticket qui vient d'être terminé
            user: L'utilisateur propriétaire du ticket
        """
        wait_str = ""
        if ticket.actual_wait_minutes is not None:
            wait_str = f" Durée du service : {ticket.actual_wait_minutes} min."

        body = f"Votre ticket {ticket.number} a été traité avec succès.{wait_str}"

        await self.save_in_app(
            title="Service terminé",
            body=body,
            org_id=ticket.org_id,
            user_id=user.id,
            ticket_id=ticket.id,
        )

        # FCM optionnel si token disponible
        if user.fcm_token:
            await self.send_fcm(
                fcm_token=user.fcm_token,
                title="Service terminé",
                body=body,
                org_id=ticket.org_id,
                user_id=user.id,
                data={
                    "type": "TICKET_DONE",
                    "ticket_id": ticket.id,
                    "ticket_number": ticket.number,
                },
                ticket_id=ticket.id,
            )

    async def notify_waiting_time_alert(
        self, ticket: Ticket, user: User, wait_minutes: int
    ) -> None:
        """
        Rules Engine : déclenché si le temps d'attente dépasse 30 minutes.
        Envoie une alerte à l'utilisateur pour l'informer du délai prolongé.

        Ce trigger est la première étape avant le ML (DÉCISION 9).
        Il doit être appelé périodiquement par un scheduler ou lors
        du recalcul de l'ETA.

        Args:
            ticket: Le ticket concerné
            user: L'utilisateur en attente
            wait_minutes: Temps d'attente estimé actuel (en minutes)
        """
        if wait_minutes <= 30:
            # Règle non déclenchée — temps acceptable
            return

        body = (
            f"Votre ticket {ticket.number} a encore environ "
            f"{wait_minutes} minutes d'attente. "
            f"Vous pouvez annuler si nécessaire."
        )

        # In-app toujours
        await self.save_in_app(
            title="Délai d'attente prolongé",
            body=body,
            org_id=ticket.org_id,
            user_id=user.id,
            ticket_id=ticket.id,
        )

        # FCM si token disponible
        if user.fcm_token:
            await self.send_fcm(
                fcm_token=user.fcm_token,
                title="Délai d'attente prolongé",
                body=body,
                org_id=ticket.org_id,
                user_id=user.id,
                data={
                    "type": "WAITING_ALERT",
                    "ticket_id": ticket.id,
                    "ticket_number": ticket.number,
                    "wait_minutes": str(wait_minutes),
                },
                ticket_id=ticket.id,
            )

        logger.info(
            f"[RULES ENGINE] Alerte attente prolongée — ticket={ticket.number} "
            f"| wait={wait_minutes}min | user={user.id}"
        )
