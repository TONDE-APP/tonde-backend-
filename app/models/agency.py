"""
Modèles Agency et Service.

NOTE ARCHITECTURE : Dans TONDE v1.0, 'Agency' sera renommé 'Branch'.
Ce fichier est conservé tel quel pour le Sprint 0.
La migration Agency → Branch sera faite en Sprint 1 via Alembic.

  Organization → Branch (Agency) → Service → Counter → Ticket
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float, Boolean, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Multi-tenant ──────────────────────────────────────────
    org_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # ── Informations de base ──────────────────────────────────
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Valeurs : bank, hospital, university, administration, other
    sector: Mapped[str] = mapped_column(String(50))

    # ── Contact ───────────────────────────────────────────────
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str] = mapped_column(String(100), default="Bujumbura")
    country: Mapped[str] = mapped_column(String(50), default="Burundi")

    # ── Géolocalisation ───────────────────────────────────────
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Horaires ──────────────────────────────────────────────
    opens_at: Mapped[str] = mapped_column(String(5), default="08:00")
    closes_at: Mapped[str] = mapped_column(String(5), default="17:00")

    # ── Branding ─────────────────────────────────────────────
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Configuration file d'attente ──────────────────────────
    max_daily_tickets: Mapped[int] = mapped_column(Integer, default=500)
    avg_service_minutes: Mapped[int] = mapped_column(Integer, default=5)

    # ── Statut ────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=False)

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

    # ── Relations ─────────────────────────────────────────────
    services: Mapped[list["Service"]] = relationship(
        "Service", back_populates="agency", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Agency {self.name}>"


class Service(Base):
    """
    Un service proposé par une agence.
    Exemples : 'Dépôt', 'Retrait', 'Consultation médicale', 'Inscription'.
    Chaque service a son propre préfixe de ticket (A, B, C...).
    """
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Multi-tenant ──────────────────────────────────────────
    org_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    agency_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agencies.id", ondelete="CASCADE")
    )

    # ── Informations ─────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Préfixe du ticket pour ce service (A, B, C...)
    ticket_prefix: Mapped[str] = mapped_column(String(5), default="A")

    # Durée moyenne d'un service en minutes (pour calcul ETA)
    avg_duration_minutes: Mapped[int] = mapped_column(Integer, default=5)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Dates ─────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relations ─────────────────────────────────────────────
    agency: Mapped["Agency"] = relationship("Agency", back_populates="services")

    def __repr__(self) -> str:
        return f"<Service {self.name} @ {self.agency_id}>"
