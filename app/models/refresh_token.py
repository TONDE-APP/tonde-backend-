"""
RefreshToken model for persistent session management.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # Stored as hash (never plaintext) for security
    token_hash: Mapped[str] = mapped_column(
        String(255),
        unique=True,
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    device_info: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        status = "valid" if not self.is_revoked else "revoked"
        return f"<RefreshToken {self.id[:8]}... ({status})>"
