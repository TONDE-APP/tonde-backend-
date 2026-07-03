"""
Modèle UserOrganization — Table 'user_organizations' dans PostgreSQL.

Table de liaison Many-to-Many entre User et Organization.
Implémente la DÉCISION 7 : un utilisateur peut appartenir à plusieurs
organisations (BANCOBU, CHUK, etc.) depuis une seule application TONDE.

Hiérarchie complète :
  User ↔ UserOrganization ↔ Organization → Branch → Service → Counter → Ticket

Note : User.org_id (champ scalaire) reste présent pour compatibilité Sprint 1.
La migration complète vers user_organizations se fait progressivement.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class UserOrganization(Base):
    """
    Appartenance d'un utilisateur à une organisation.

    Un enregistrement actif (status='active') signifie que l'utilisateur
    peut interagir avec cette organisation : prendre des tickets, voir
    les branches, etc.

    Plusieurs enregistrements pour le même user_id sont possibles —
    un par organisation rejointe.
    """
    __tablename__ = "user_organizations"

    # Contrainte d'unicité : un user ne peut rejoindre la même org qu'une seule fois
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_user_organization"),
    )

    # ── Identifiant ───────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Relations Many-to-Many ────────────────────────────────
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Numéro de membre (optionnel) ──────────────────────────
    # Utilisé pour le "Join by Number" (S2-08) :
    # numéro de compte bancaire, numéro de dossier patient, etc.
    member_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    # ── Statut de l'appartenance ──────────────────────────────
    # active   : l'utilisateur est membre actif
    # inactive : désactivé (quitter l'org ou révocation admin)
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )

    # ── Dates ─────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relations ORM ─────────────────────────────────────────
    organization: Mapped["Organization"] = relationship(  # noqa: F821
        "Organization", back_populates="user_organizations"
    )
    user: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="user_organizations"
    )

    def __repr__(self) -> str:
        return f"<UserOrganization user={self.user_id} org={self.organization_id} status={self.status}>"
