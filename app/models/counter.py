"""
Modèle Counter — Table 'counters' dans PostgreSQL.

Un Counter (guichet) est le point physique où un agent
sert les clients. Chaque guichet appartient à une Branch (agence)
et à une Organisation.

Un guichet peut être ouvert, fermé ou en pause.
Le champ current_ticket_id stocke le ticket en cours de service.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Counter(Base):
    __tablename__ = "counters"

    # ── Identifiant ───────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Multi-tenant ──────────────────────────────────────────
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )

    # ── Appartenance à une agence ─────────────────────────────
    agency_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        index=True,
    )

    # ── Identité ──────────────────────────────────────────────
    # Nom affiché sur l'écran de la salle d'attente
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Ticket en cours ───────────────────────────────────────
    # ID du ticket actuellement en cours de service (NULL si guichet libre)
    current_ticket_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )

    # ── Statut ────────────────────────────────────────────────
    is_open: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Dates ─────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        status = "ouvert" if self.is_open else "fermé"
        return f"<Counter {self.name} ({status})>"
