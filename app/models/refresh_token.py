"""
Modèle RefreshToken — Table 'refresh_tokens' dans PostgreSQL.

Utilisé pour la persistance des sessions JWT.
Quand un client rafraîchit son access token via refresh_token,
le backend vérifie la validité du refresh token en base.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, ForeignKey
Permet la révocation de session, la rotation de token et le support multi-device.
Le token JWT brut n'est jamais stocké — uniquement son SHA-256.

Architecture :
  - Un enregistrement par session active (une ligne par device)
  - revoked_at NULL  → session valide
  - revoked_at non-NULL → session révoquée
  - Cascade DELETE sur users.id → suppression automatique à la suppression du compte
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    # ── Identifiant ─────────────────────────────────────────────
    # ── Identifiant ───────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Lien vers l'utilisateur ──────────────────────────────────
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # ── Token ───────────────────────────────────────────────────
    # Stocké en hash (jamais en clair) pour la sécurité
    token_hash: Mapped[str] = mapped_column(
        String(255),
        unique=True,
    )

    # ── Expiration ───────────────────────────────────────────────
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # ── Dates ─────────────────────────────────────────────────
    # ── Propriétaire — cascade delete si le user est supprimé ─
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Hash SHA-256 du JWT brut (64 hex chars) ───────────────
    # Jamais le token en clair. Contrainte UNIQUE pour lookup rapide.
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    # ── Tracking multi-device ─────────────────────────────────
    # Identifiant opaque fourni par le client (ex: "flutter-android-pixel7")
    device_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # ── IP du client à l'émission (audit) ────────────────────
    ip_address: Mapped[str | None] = mapped_column(
        String(45),  # IPv4 (15) ou IPv6 (45)
        nullable=True,
    )

    # ── Expiration (copie du payload JWT exp) ────────────────
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # ── Révocation ────────────────────────────────────────────
    # NULL = session active | non-NULL = session révoquée
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Date d'émission ───────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Statut ────────────────────────────────────────────────
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Traçabilité ────────────────────────────────────────────
    device_info: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        status = "valide" if not self.is_revoked else "révoqué"
        return f"<RefreshToken {self.id[:8]}... ({status})>"
    # ── Index composite pour logout/all (sessions actives par user) ──
    __table_args__ = (
        Index("ix_refresh_tokens_user_active", "user_id", "revoked_at"),
    )

    @property
    def is_valid(self) -> bool:
        """True si le token n'est pas révoqué et n'est pas expiré."""
        return (
            self.revoked_at is None
            and datetime.now(timezone.utc) < self.expires_at
        )

    def __repr__(self) -> str:
        status = "active" if self.revoked_at is None else "revoked"
        return f"<RefreshToken user={self.user_id} device={self.device_id} {status}>"
