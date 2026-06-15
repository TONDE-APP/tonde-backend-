"""
Tests unitaires — AuthService

Règle de patching : toujours patcher dans le module qui importe la fonction,
pas dans le module source. Ex: "app.services.auth_service.get_otp"
et non "app.core.redis.get_otp".
"""
import pytest
from unittest.mock import patch, AsyncMock

from app.schemas.auth import (
    RegisterPhoneRequest, VerifyOtpRequest,
    RegisterEmailRequest, LoginEmailRequest,
)
from app.core.security import DEV_OTP


# ── register_phone ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_phone_returns_success(auth_service):
    """En dev, register_phone retourne success avec expires_in_seconds."""
    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.increment_register_attempts", new_callable=AsyncMock, return_value=1):
            with patch("app.services.auth_service.save_otp", new_callable=AsyncMock):
                result = await auth_service.register_phone(
                    RegisterPhoneRequest(phone="+25779123456")
                )

    assert result["success"] is True
    assert result["otp_sent"] is True
    assert "expires_in_seconds" in result


@pytest.mark.asyncio
async def test_register_phone_dev_otp_exposed(auth_service):
    """En développement, dev_otp est inclus dans la réponse."""
    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.increment_register_attempts", new_callable=AsyncMock, return_value=1):
            with patch("app.services.auth_service.save_otp", new_callable=AsyncMock):
                result = await auth_service.register_phone(
                    RegisterPhoneRequest(phone="+25779123456")
                )
    assert "dev_otp" in result


# ── verify_otp ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_otp_creates_user_and_returns_jwt(auth_service):
    """Premier login par OTP crée automatiquement le compte et retourne JWT."""
    phone = "+25779999888"

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=DEV_OTP):
            with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=1):
                with patch("app.services.auth_service.delete_otp", new_callable=AsyncMock):
                    result = await auth_service.verify_otp(
                        VerifyOtpRequest(phone=phone, otp=DEV_OTP)
                    )

    assert result.access_token is not None
    assert result.refresh_token is not None
    assert result.user.phone == phone
    assert result.user.role == "client"
    assert result.user.is_verified is True


@pytest.mark.asyncio
async def test_verify_otp_expired_raises_400(auth_service):
    """OTP expiré (absent de Redis) → HTTP 400."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.verify_otp(
                    VerifyOtpRequest(phone="+25779111222", otp="123456")
                )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "OTP_EXPIRED"


@pytest.mark.asyncio
async def test_verify_otp_invalid_raises_400(auth_service):
    """OTP incorrect → HTTP 400 avec nombre de tentatives restantes."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value="654321"):
            with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=1):
                with pytest.raises(HTTPException) as exc_info:
                    await auth_service.verify_otp(
                        VerifyOtpRequest(phone="+25779111222", otp="000000")
                    )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_OTP"
    assert "attempts_remaining" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_otp_too_many_attempts_raises_429(auth_service):
    """Trop de tentatives (compteur > max) → HTTP 429 + blocage numéro."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value="123456"):
            with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=99):
                with patch("app.services.auth_service.block_phone", new_callable=AsyncMock):
                    with pytest.raises(HTTPException) as exc_info:
                        await auth_service.verify_otp(
                            VerifyOtpRequest(phone="+25779111222", otp="999999")
                        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "PHONE_BLOCKED"


# ── register_email ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_email_success(auth_service):
    """Inscription email crée le compte et retourne JWT."""
    result = await auth_service.register_email(
        RegisterEmailRequest(
            email="agent@coopec.bi",
            password="SecurePass123",
            name="Jean Ndayishimiye",
        )
    )

    assert result.access_token is not None
    assert result.user.email == "agent@coopec.bi"
    assert result.user.name == "Jean Ndayishimiye"


@pytest.mark.asyncio
async def test_register_email_duplicate_raises_409(auth_service):
    """Email déjà utilisé → HTTP 409."""
    from fastapi import HTTPException

    data = RegisterEmailRequest(
        email="agent@coopec.bi",
        password="SecurePass123",
        name="Jean Ndayishimiye",
    )
    await auth_service.register_email(data)

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.register_email(data)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "EMAIL_EXISTS"


# ── login_email ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_email_success(auth_service):
    """Login avec les bons credentials retourne JWT."""
    email = "admin@tonde.bi"
    password = "MyPassword456"

    await auth_service.register_email(
        RegisterEmailRequest(email=email, password=password, name="Admin")
    )
    result = await auth_service.login_email(
        LoginEmailRequest(email=email, password=password)
    )

    assert result.access_token is not None
    assert result.user.email == email


@pytest.mark.asyncio
async def test_login_email_wrong_password_raises_401(auth_service):
    """Mauvais mot de passe → HTTP 401."""
    from fastapi import HTTPException

    email = "admin2@tonde.bi"
    await auth_service.register_email(
        RegisterEmailRequest(email=email, password="CorrectPass", name="Admin")
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.login_email(
            LoginEmailRequest(email=email, password="WrongPass")
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "INVALID_CREDENTIALS"


# ── refresh_token ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_token_success(auth_service):
    """Refresh token valide retourne un nouvel access token."""
    auth_result = await auth_service.register_email(
        RegisterEmailRequest(email="refresh@test.bi", password="Pass1234", name="Test")
    )
    result = await auth_service.refresh_token(auth_result.refresh_token)

    assert result["success"] is True
    assert result["access_token"] is not None


@pytest.mark.asyncio
async def test_refresh_token_invalid_raises_401(auth_service):
    """Refresh token invalide → HTTP 401."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.refresh_token("token.invalide.xxx")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "INVALID_REFRESH_TOKEN"


# ── Rate limiting / Blocage numéro ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_phone_blocked_raises_429(auth_service):
    """Numéro bloqué suite à trop d'échecs → HTTP 429 sur register aussi."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(True, 840)):
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.register_phone(
                RegisterPhoneRequest(phone="+25779123456")
            )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "PHONE_BLOCKED"
    assert "retry_after_seconds" in exc_info.value.detail
    assert exc_info.value.detail["retry_after_seconds"] == 840


@pytest.mark.asyncio
async def test_register_phone_sms_spam_raises_429(auth_service):
    """Trop de demandes de SMS sur un même numéro → HTTP 429."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.increment_register_attempts", new_callable=AsyncMock, return_value=4):
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.register_phone(
                    RegisterPhoneRequest(phone="+25779123456")
                )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "SMS_RATE_LIMIT"
    assert exc_info.value.detail["retry_after_seconds"] == 60


@pytest.mark.asyncio
async def test_verify_otp_blocked_phone_raises_429(auth_service):
    """Numéro déjà bloqué → HTTP 429 immédiat sur verify-otp."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(True, 600)):
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.verify_otp(
                VerifyOtpRequest(phone="+25779111222", otp="123456")
            )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "PHONE_BLOCKED"
    assert exc_info.value.detail["retry_after_seconds"] == 600


@pytest.mark.asyncio
async def test_verify_otp_last_attempt_triggers_block(auth_service):
    """Dernière tentative épuisée → numéro bloqué et 429."""
    from fastapi import HTTPException
    from app.core.config import settings

    max_attempts = settings.OTP_MAX_ATTEMPTS

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value="111111"):
            with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=max_attempts):
                with patch("app.services.auth_service.block_phone", new_callable=AsyncMock) as mock_block:
                    with pytest.raises(HTTPException) as exc_info:
                        await auth_service.verify_otp(
                            VerifyOtpRequest(phone="+25779000111", otp="999999")
                        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "PHONE_BLOCKED"
    mock_block.assert_called_once()  # Le blocage a bien été déclenché


@pytest.mark.asyncio
async def test_verify_otp_invalid_shows_remaining_attempts(auth_service):
    """OTP incorrect → message indique combien de tentatives restantes."""
    from fastapi import HTTPException
    from app.core.config import settings

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value="111111"):
            with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=2):
                with pytest.raises(HTTPException) as exc_info:
                    await auth_service.verify_otp(
                        VerifyOtpRequest(phone="+25779000111", otp="999999")
                    )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_OTP"
    remaining = exc_info.value.detail["attempts_remaining"]
    assert remaining == settings.OTP_MAX_ATTEMPTS - 2
    assert remaining > 0
