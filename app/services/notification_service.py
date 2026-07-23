"""
NotificationService — SMS (Africa's Talking) + FCM (Firebase) + In-App.

Responsabilités :
  - Envoyer des SMS via Africa's Talking (marché Afrique)
  - Envoyer des push notifications via Firebase FCM (httpx async)
  - Persister chaque notification dans la table 'notifications' (audit trail)
  - Exposer des méthodes de trigger liées aux événements tickets

Triggers principaux :
  - notify_ticket_called()     → SMS + FCM au client quand son ticket est appelé
  - notify_ticket_done()       → In-app quand le service est terminé
  - notify_long_wait_alert()   → SMS si temps d'attente > seuil branch

En ENVIRONMENT=development : les envois réels sont simulés (log uniquement).
En production : Africa's Talking et FCM sont appelés réellement.
"""
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.notification import Notification, NotificationChannel, NotificationStatus
from app.models.user import User
from app.models.ticket import Ticket

logger = logging.getLogger(__name__)


class NotificationService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Triggers métier ───────────────────────────────────────────────────────

    async def notify_ticket_called(
        self,
        ticket: Ticket,
        counter_name: str,
    ) -> None:
        """
        Notifie le client que son ticket est appelé.

        Envoie :
          - SMS : "Votre ticket A-12 est appelé au guichet Caisse 1. Présentez-vous maintenant."
          - FCM : push notification si l'app est installée

        Args:
            ticket: Le ticket qui vient d'être appelé
            counter_name: Nom du guichet affiché au client
        """
        user = await self._get_user(ticket.user_id)
        if not user:
            return

        message = (
            f"TONDE — Votre ticket {ticket.number} est appelé "
            f"au guichet {counter_name}. Présentez-vous maintenant."
        )

        # SMS
        if user.phone:
            await self._send_sms(
                org_id=ticket.org_id,
                user_id=user.id,
                ticket_id=ticket.id,
                phone=user.phone,
                body=message,
            )

        # FCM
        if user.fcm_token:
            await self._send_fcm(
                org_id=ticket.org_id,
                user_id=user.id,
                ticket_id=ticket.id,
                fcm_token=user.fcm_token,
                title=f"Ticket {ticket.number} appelé",
                body=message,
            )

    async def notify_ticket_done(self, ticket: Ticket) -> None:
        """
        Notifie le client que son service est terminé.
        Notification in-app uniquement.

        Args:
            ticket: Le ticket terminé (status=DONE)
        """
        user = await self._get_user(ticket.user_id)
        if not user:
            return

        message = (
            f"TONDE — Service terminé pour votre ticket {ticket.number}. "
            "Merci de votre visite !"
        )

        await self._save_notification(
            org_id=ticket.org_id,
            user_id=user.id,
            ticket_id=ticket.id,
            channel=NotificationChannel.IN_APP,
            title=f"Service terminé — {ticket.number}",
            body=message,
            status=NotificationStatus.SENT,
        )

    async def notify_long_wait_alert(
        self,
        ticket: Ticket,
        wait_minutes: int,
        threshold_minutes: int,
    ) -> None:
        """
        Alerte le client si son temps d'attente dépasse le seuil configuré.
        Rules Engine DÉCISION 9 : si waiting_time > seuil → SMS d'alerte.

        Args:
            ticket: Le ticket en attente
            wait_minutes: Temps d'attente actuel en minutes
            threshold_minutes: Seuil configuré sur la branch
        """
        user = await self._get_user(ticket.user_id)
        if not user or not user.phone:
            return

        message = (
            f"TONDE — Votre ticket {ticket.number} attend depuis {wait_minutes} min. "
            f"Vous serez appelé prochainement. Restez disponible."
        )

        await self._send_sms(
            org_id=ticket.org_id,
            user_id=user.id,
            ticket_id=ticket.id,
            phone=user.phone,
            body=message,
        )

    # ── Canaux d'envoi ────────────────────────────────────────────────────────

    async def _send_sms(
        self,
        org_id: str,
        user_id: str,
        ticket_id: str | None,
        phone: str,
        body: str,
    ) -> None:
        """
        Envoie un SMS via Africa's Talking.

        En développement : simule l'envoi (log uniquement, pas d'appel réseau).
        En production : appelle l'API Africa's Talking réellement.

        Args:
            org_id: Organisation pour l'audit trail
            user_id: Destinataire
            ticket_id: Ticket concerné (optionnel)
            phone: Numéro de téléphone au format international (+25712345678)
            body: Corps du SMS (max 160 chars recommandé)
        """
        is_dev = settings.ENVIRONMENT == "development"

        if is_dev:
            logger.info(f"[SMS DEV] → {phone} : {body}")
            await self._save_notification(
                org_id=org_id,
                user_id=user_id,
                ticket_id=ticket_id,
                channel=NotificationChannel.SMS,
                body=body,
                status=NotificationStatus.SENT,
            )
            return

        # ── Envoi réel via Africa's Talking ───────────────────────────────────
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.africastalking.com/version1/messaging",
                    headers={
                        "apiKey": settings.AFRICAS_TALKING_API_KEY,
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                    data={
                        "username": settings.AFRICAS_TALKING_USERNAME,
                        "to": phone,
                        "message": body,
                        "from": settings.AFRICAS_TALKING_SENDER_ID,
                    },
                )
                response.raise_for_status()

            logger.info(f"[SMS] Envoyé → {phone}")
            await self._save_notification(
                org_id=org_id,
                user_id=user_id,
                ticket_id=ticket_id,
                channel=NotificationChannel.SMS,
                body=body,
                status=NotificationStatus.SENT,
            )

        except Exception as e:
            logger.error(f"[SMS] Échec envoi → {phone} : {e}")
            await self._save_notification(
                org_id=org_id,
                user_id=user_id,
                ticket_id=ticket_id,
                channel=NotificationChannel.SMS,
                body=body,
                status=NotificationStatus.FAILED,
                error_message=str(e)[:500],
            )

    async def _send_fcm(
        self,
        org_id: str,
        user_id: str,
        ticket_id: str | None,
        fcm_token: str,
        title: str,
        body: str,
    ) -> None:
        """
        Envoie une push notification via Firebase Cloud Messaging (Legacy HTTP API).

        En développement : simule l'envoi (log uniquement).
        En production : appelle l'API FCM via httpx async.

        Args:
            org_id: Organisation pour l'audit trail
            user_id: Destinataire
            ticket_id: Ticket concerné (optionnel)
            fcm_token: Token FCM de l'appareil mobile du client
            title: Titre de la notification push
            body: Corps de la notification
        """
        is_dev = settings.ENVIRONMENT == "development"

        if is_dev:
            logger.info(f"[FCM DEV] → {fcm_token[:20]}... title={title}")
            await self._save_notification(
                org_id=org_id,
                user_id=user_id,
                ticket_id=ticket_id,
                channel=NotificationChannel.FCM,
                title=title,
                body=body,
                status=NotificationStatus.SENT,
            )
            return

        if not settings.FIREBASE_SERVER_KEY:
            logger.warning("[FCM] FIREBASE_SERVER_KEY non configuré — envoi ignoré")
            return

        # ── Envoi réel via FCM Legacy API ─────────────────────────────────────
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://fcm.googleapis.com/fcm/send",
                    headers={
                        "Authorization": f"key={settings.FIREBASE_SERVER_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "to": fcm_token,
                        "notification": {
                            "title": title,
                            "body": body,
                            "sound": "default",
                        },
                        "data": {
                            "ticket_id": ticket_id or "",
                            "type": "ticket_event",
                        },
                        "priority": "high",
                    },
                )
                response.raise_for_status()

            logger.info(f"[FCM] Envoyé → user={user_id}")
            await self._save_notification(
                org_id=org_id,
                user_id=user_id,
                ticket_id=ticket_id,
                channel=NotificationChannel.FCM,
                title=title,
                body=body,
                status=NotificationStatus.SENT,
            )

        except Exception as e:
            logger.error(f"[FCM] Échec envoi → user={user_id} : {e}")
            await self._save_notification(
                org_id=org_id,
                user_id=user_id,
                ticket_id=ticket_id,
                channel=NotificationChannel.FCM,
                title=title,
                body=body,
                status=NotificationStatus.FAILED,
                error_message=str(e)[:500],
            )

    # ── Helpers privés ────────────────────────────────────────────────────────

    async def _save_notification(
        self,
        org_id: str,
        user_id: str,
        ticket_id: str | None,
        channel: NotificationChannel,
        body: str,
        status: NotificationStatus,
        title: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        Persiste une notification dans la table 'notifications'.
        Appelé après chaque tentative d'envoi (succès ou échec).
        """
        notif = Notification(
            id=str(uuid.uuid4()),
            org_id=org_id,
            user_id=user_id,
            ticket_id=ticket_id,
            channel=channel,
            title=title,
            body=body,
            status=status,
            error_message=error_message,
            sent_at=datetime.now(timezone.utc) if status == NotificationStatus.SENT else None,
        )
        self.db.add(notif)
        await self.db.commit()

    async def _get_user(self, user_id: str) -> User | None:
        """Récupère l'utilisateur pour accéder à son phone et fcm_token."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
