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

    with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.verify_otp(
                VerifyOtpRequest(phone="+25779111222", otp="123456")
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "OTP_EXPIRED"


@pytest.mark.asyncio
async def test_verify_otp_invalid_raises_400(auth_service):
    """OTP incorrect → HTTP 400."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value="654321"):
        with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=1):
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.verify_otp(
                    VerifyOtpRequest(phone="+25779111222", otp="000000")
                )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_OTP"


@pytest.mark.asyncio
async def test_verify_otp_too_many_attempts_raises_429(auth_service):
    """Trop de tentatives → HTTP 429."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value="123456"):
        with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=4):
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.verify_otp(
                    VerifyOtpRequest(phone="+25779111222", otp="999999")
                )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "TOO_MANY_ATTEMPTS"


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
