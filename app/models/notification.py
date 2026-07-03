"""
Modèle Notification — Table 'notifications' dans PostgreSQL.

Chaque notification envoyée (SMS, FCM, in-app) est persistée
pour l'audit trail et les analytics.

Channels supportés :
  - SMS via Africa's Talking
  - FCM via Firebase Cloud Messaging (httpx)
  - In-app (stocké uniquement, pas d'envoi réseau)
"""
import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Enum as SAEnum, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class NotificationChannel(str, enum.Enum):
    SMS    = "sms"     # Africa's Talking
    FCM    = "fcm"     # Firebase Cloud Messaging (push)
    IN_APP = "in_app"  # Notification in-app (pas d'envoi externe)


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"  # En attente d'envoi
    SENT    = "sent"     # Envoyée avec succès
    FAILED  = "failed"   # Échec de l'envoi (loggé pour retry)


class Notification(Base):
    __tablename__ = "notifications"

    # ── Identifiant unique ────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Multi-tenant ──────────────────────────────────────────
    # Obligatoire sur toutes les entités métier (règle absolue)
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )

    # ── Destinataire ──────────────────────────────────────────
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # ── Ticket associé (optionnel — certaines notifs sont générales) ──────────
    ticket_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Contenu ───────────────────────────────────────────────
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(NotificationChannel),
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text)

    # ── Statut et traçabilité ─────────────────────────────────
    status: Mapped[NotificationStatus] = mapped_column(
        SAEnum(NotificationStatus),
        default=NotificationStatus.PENDING,
        index=True,
    )
    # True si l'utilisateur a lu la notification (in-app uniquement)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    # Message d'erreur si status=FAILED (pour debug et retry)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Dates ─────────────────────────────────────────────────
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<Notification {self.channel} → user={self.user_id} [{self.status}]>"
