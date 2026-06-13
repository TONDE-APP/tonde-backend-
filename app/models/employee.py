"""
Modèle Employee — Table 'employees' dans PostgreSQL.

Un Employee est le lien entre un User et une Organisation.
Il définit le rôle opérationnel de l'utilisateur au sein
de l'organisation (quel guichet, quelle agence).

Un même User peut être Employee dans plusieurs organisations
(cas rare, mais possible pour les consultants).
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.user import UserRole
import enum


class EmployeeStatus(str, enum.Enum):
    ACTIVE    = "active"     # En service
    ON_LEAVE  = "on_leave"   # En congé
    SUSPENDED = "suspended"  # Suspendu temporairement
    INACTIVE  = "inactive"   # Désactivé


class Employee(Base):
    __tablename__ = "employees"

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

    # ── Lien vers l'utilisateur système ──────────────────────
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # ── Affectation ───────────────────────────────────────────
    # Agence d'affectation principale
    agency_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agencies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Guichet attribué (peut changer selon les jours)
    counter_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("counters.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Rôle dans l'organisation ──────────────────────────────
    # Copie du UserRole — source de vérité pour RBAC dans ce contexte
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole))

    # ── Statut ────────────────────────────────────────────────
    status: Mapped[EmployeeStatus] = mapped_column(
        SAEnum(EmployeeStatus),
        default=EmployeeStatus.ACTIVE,
    )

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
        return f"<Employee user={self.user_id} org={self.org_id} role={self.role}>"
