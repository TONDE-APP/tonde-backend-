"""
Tests unitaires — AuthService

Règle de patching : toujours patcher dans le module qui importe la fonction,
pas dans le module source. Ex: "app.services.auth_service.get_otp"
et non "app.core.redis.get_otp".

Les tests TASK-02 (RefreshToken DB, logout, logout_all) seront ajoutés
dans une PR dédiée quand le modèle RefreshToken sera intégré à main.
"""
import hashlib
import pytest
from unittest.mock import patch, AsyncMock

from app.schemas.auth import (
    RegisterPhoneRequest, VerifyOtpRequest,
    RegisterEmailRequest, LoginEmailRequest,
)
from app.core.security import DEV_OTP

# Hash SHA-256 du DEV_OTP "123456" — utilisé dans tous les mocks get_otp
DEV_OTP_HASH = hashlib.sha256(DEV_OTP.encode()).hexdigest()


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
    assert result["dev_otp"] == DEV_OTP


@pytest.mark.asyncio
async def test_register_phone_blocked_raises_429(auth_service):
    """Numéro bloqué → HTTP 429 immédiat."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(True, 600)):
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.register_phone(RegisterPhoneRequest(phone="+25779123456"))

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "PHONE_BLOCKED"


# ── verify_otp ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_otp_creates_user_and_returns_jwt(auth_service):
    """Premier login par OTP crée automatiquement le compte et retourne JWT."""
    phone = "+25779999888"

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=DEV_OTP_HASH):
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
    """OTP incorrect → HTTP 400 avec attempts_remaining."""
    from fastapi import HTTPException

    # Stocker le hash de "654321" — soumettre "000000"
    wrong_hash = hashlib.sha256("654321".encode()).hexdigest()

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=wrong_hash):
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
    """Compteur > OTP_MAX_ATTEMPTS → HTTP 429 PHONE_BLOCKED."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=DEV_OTP_HASH):
            with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=4):
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


@pytest.mark.asyncio
async def test_refresh_token_disabled_user_raises_403(auth_service):
    """Compte désactivé → refresh token rejeté HTTP 403."""
    from fastapi import HTTPException
    from sqlalchemy import select
    from app.models.user import User

    auth_result = await auth_service.register_email(
        RegisterEmailRequest(email="disabled@test.bi", password="Pass1234", name="Disabled")
    )

    # Désactiver le compte manuellement
    result = await auth_service.db.execute(
        select(User).where(User.email == "disabled@test.bi")
    )
    user = result.scalar_one()
    user.is_active = False
    await auth_service.db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.refresh_token(auth_result.refresh_token)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "ACCOUNT_DISABLED"


# ── Tests hashage OTP ─────────────────────────────────────────────────────────

def test_hash_otp_deterministic_and_64_chars():
    """_hash_otp produit toujours 64 caractères hex et est déterministe."""
    from app.core.redis import _hash_otp

    h1 = _hash_otp("123456")
    h2 = _hash_otp("123456")

    assert h1 == h2
    assert len(h1) == 64
    assert h1 != "123456"
    assert _hash_otp("123456") != _hash_otp("654321")


@pytest.mark.asyncio
async def test_otp_stored_as_hash_not_plaintext():
    """save_otp stocke le hash SHA-256, jamais l'OTP en clair."""
    captured = {}

    async def fake_setex(key, ttl, value):
        if "otp:" in key and "attempts" not in key:
            captured["value"] = value

    mock_r = AsyncMock()
    mock_r.setex = AsyncMock(side_effect=fake_setex)

    with patch("app.core.redis.get_redis", return_value=mock_r):
        from app.core.redis import save_otp
        await save_otp("+25779000001", DEV_OTP)

    assert "value" in captured
    expected = hashlib.sha256(DEV_OTP.encode()).hexdigest()
    assert captured["value"] == expected
    assert captured["value"] != DEV_OTP
    assert len(captured["value"]) == 64


@pytest.mark.asyncio
async def test_verify_otp_with_correct_hash_succeeds(auth_service):
    """verify_otp réussit quand get_otp retourne sha256(otp_correct)."""
    phone = "+25779000002"

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=DEV_OTP_HASH):
            with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=1):
                with patch("app.services.auth_service.delete_otp", new_callable=AsyncMock):
                    result = await auth_service.verify_otp(
                        VerifyOtpRequest(phone=phone, otp=DEV_OTP)
                    )

    assert result.access_token is not None
    assert result.refresh_token is not None


@pytest.mark.asyncio
async def test_verify_otp_with_wrong_code_fails(auth_service):
    """verify_otp échoue quand le hash de l'OTP soumis ne correspond pas."""
    from fastapi import HTTPException

    wrong_hash = hashlib.sha256("654321".encode()).hexdigest()

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=wrong_hash):
            with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=1):
                with pytest.raises(HTTPException) as exc_info:
                    await auth_service.verify_otp(
                        VerifyOtpRequest(phone="+25779000003", otp="000000")
                    )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_OTP"


@pytest.mark.asyncio
async def test_dev_otp_123456_still_works(auth_service):
    """DEV_OTP '123456' fonctionne en mode development via le hash."""
    phone = "+25779000004"

    with patch("app.services.auth_service.is_phone_blocked", new_callable=AsyncMock, return_value=(False, 0)):
        with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=DEV_OTP_HASH):
            with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=1):
                with patch("app.services.auth_service.delete_otp", new_callable=AsyncMock):
                    result = await auth_service.verify_otp(
                        VerifyOtpRequest(phone=phone, otp="123456")
                    )

    assert result.access_token is not None
    assert result.user.is_verified is True
