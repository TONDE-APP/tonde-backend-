"""
Modèle Organization — Table 'organizations' dans PostgreSQL.

Une Organization est la racine du multi-tenant dans TONDE.
Exemples : Banque Coopec Burundi, CHU Kamenge, Université du Burundi.

Hiérarchie complète :
  Organization → Branch → Service → Counter → Ticket
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    # ── Identifiant ───────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Identité ──────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Secteur d'activité ────────────────────────────────────
    # Valeurs attendues : bank, hospital, university, administration, other
    sector: Mapped[str] = mapped_column(String(50))

    # ── Localisation ─────────────────────────────────────────
    country: Mapped[str] = mapped_column(String(50), default="Burundi")
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Contact ───────────────────────────────────────────────
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Logo ──────────────────────────────────────────────────
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Statut ────────────────────────────────────────────────
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

    # ── Relations ─────────────────────────────────────────────
    # NOTE : relation vers Agency (qui deviendra Branch en Sprint 1)
    agencies: Mapped[list["Agency"]] = relationship(  # noqa: F821
        "Agency", foreign_keys="Agency.org_id", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Organization {self.name} ({self.sector})>"
