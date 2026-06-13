"""
Modèle Utilisateur — Table 'users' dans PostgreSQL.

Un User peut être un client mobile, un agent guichetier,
un superviseur, un admin d'agence, un admin d'organisation
ou un super-admin Tonde.

Le champ org_id permet l'isolation multi-tenant.
Les clients (role=CLIENT) ont org_id=NULL car ils ne
sont pas attachés à une organisation spécifique.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
import enum


class UserRole(str, enum.Enum):
    CLIENT       = "client"        # Utilisateur mobile — pas d'org_id
    AGENT        = "agent"         # Guichetier
    SUPERVISOR   = "supervisor"    # Responsable de salle
    ADMIN_AGENCY = "admin_agency"  # Admin d'une agence (Branch)
    ADMIN_ORG    = "admin_org"     # Admin de toute l'organisation
    SUPER_ADMIN  = "super_admin"   # Équipe Tonde — accès total


class User(Base):
    __tablename__ = "users"

    # ── Identifiant unique ────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Multi-tenant : organisation d'appartenance ────────────
    # NULL pour les clients — rempli pour agents, superviseurs, admins
    org_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Informations personnelles ─────────────────────────────
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Mot de passe (haché bcrypt — jamais en clair) ─────────
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Rôle RBAC ─────────────────────────────────────────────
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole),
        default=UserRole.CLIENT,
    )

    # ── Préférences ───────────────────────────────────────────
    language: Mapped[str] = mapped_column(String(5), default="fr")

    # ── Statut ────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Token Firebase Cloud Messaging (push notifications) ───
    fcm_token: Mapped[str | None] = mapped_column(String(500), nullable=True)

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
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<User {self.phone or self.email} ({self.role})>"
