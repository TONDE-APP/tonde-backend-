"""
Modèle RefreshToken — Table 'refresh_tokens' dans PostgreSQL.

Utilisé pour la persistance des sessions JWT.
Quand un client rafraîchit son access token via refresh_token,
le backend vérifie la validité du refresh token en base.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    # ── Identifiant ─────────────────────────────────────────────
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
