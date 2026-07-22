"""
Modèle QueueLog — Table 'queue_logs' dans PostgreSQL.

Audit trail de chaque transition d'état d'un ticket.
Chaque changement de statut génère une ligne immuable dans cette table.

Utilité :
  - Audit trail complet (qui a fait quoi, quand)
  - Source de données pour le pipeline Analytics (S2-06)
  - Calcul des métriques DÉCISION 9 :
      * Temps d'attente réel par agence/service/heure
      * Temps de traitement par agent / Pics horaires
      * Taux d'absence (ABSENT / total CALLED)

Règle : ces lignes ne sont jamais modifiées ni supprimées.
"""
import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Enum as SAEnum, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class QueueLogAction(str, enum.Enum):
    TICKET_CREATED     = "ticket_created"
    TICKET_CALLED      = "ticket_called"
    TICKET_SERVING     = "ticket_serving"
    TICKET_DONE        = "ticket_done"
    TICKET_ABSENT      = "ticket_absent"
    TICKET_RETURNED    = "ticket_returned"
    TICKET_TRANSFERRED = "ticket_transferred"
    TICKET_CANCELLED   = "ticket_cancelled"
    TICKET_INCOMPLETE  = "ticket_incomplete"


class QueueLog(Base):
    __tablename__ = "queue_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    agency_id: Mapped[str] = mapped_column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str] = mapped_column(String(36), ForeignKey("services.id", ondelete="CASCADE"), index=True)
    action: Mapped[QueueLogAction] = mapped_column(SAEnum(QueueLogAction), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    counter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    counter_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    def __repr__(self) -> str:
        return f"<QueueLog {self.action} | {self.from_status} → {self.to_status}>"
