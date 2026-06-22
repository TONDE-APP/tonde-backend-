"""
Tests unitaires — AuthService

Règle de patching : toujours patcher dans le module qui importe la fonction,
pas dans le module source. Ex: "app.services.auth_service.get_otp"
et non "app.core.redis.get_otp".

TASK-01 : Les mocks de get_otp retournent désormais le hash SHA-256
          de l'OTP attendu, jamais la valeur en clair.
"""
import hashlib
import pytest
from unittest.mock import patch, AsyncMock

from app.schemas.auth import (
    RegisterPhoneRequest, VerifyOtpRequest,
    RegisterEmailRequest, LoginEmailRequest,
)
from app.core.security import DEV_OTP

# Hash SHA-256 du DEV_OTP "123456" — utilisé dans tous les mocks
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
    """En développement, dev_otp est inclus dans la réponse (valeur en clair pour les tests)."""
    with patch("app.services.auth_service.save_otp", new_callable=AsyncMock):
        result = await auth_service.register_phone(
            RegisterPhoneRequest(phone="+25779123456")
        )
    assert "dev_otp" in result
    # Le dev_otp dans la réponse est en clair pour les tests — le hash est en Redis
    assert result["dev_otp"] == DEV_OTP


# ── verify_otp ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_otp_creates_user_and_returns_jwt(auth_service):
    """Premier login par OTP crée automatiquement le compte et retourne JWT."""
    phone = "+25779999888"

    # Mock retourne le HASH, pas le clair
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
    """OTP incorrect → HTTP 400. Mock retourne le hash de "654321"."""
    from fastapi import HTTPException

    wrong_hash = hashlib.sha256("654321".encode()).hexdigest()
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
    """Trop de tentatives (compteur > max) → HTTP 429 + blocage numéro."""
    from fastapi import HTTPException

    with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=DEV_OTP_HASH):
        with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=4):
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


# ── TASK-01 : nouveaux tests hashage OTP ──────────────────────────────────────

@pytest.mark.asyncio
async def test_otp_stored_as_hash_not_plaintext(auth_service):
    """save_otp stocke le hash SHA-256 dans Redis, jamais l'OTP en clair."""
    from app.core.redis import _hash_otp

    captured_value = None

    async def fake_setex(key, ttl, value):
        nonlocal captured_value
        if "otp:" in key and "attempts" not in key:
            captured_value = value

    with patch("app.services.auth_service.save_otp", new_callable=AsyncMock) as mock_save:
        # On utilise la vraie fonction save_otp pour capturer l'appel Redis
        pass

    # Tester directement _hash_otp et save_otp
    from unittest.mock import AsyncMock as AM, MagicMock
    mock_r = AM()
    mock_r.setex = AM(side_effect=fake_setex)

    with patch("app.core.redis.get_redis", return_value=mock_r):
        from app.core.redis import save_otp
        await save_otp("+25779000001", DEV_OTP)

    expected_hash = hashlib.sha256(DEV_OTP.encode()).hexdigest()
    assert captured_value == expected_hash, "L'OTP doit être stocké hashé, pas en clair"
    assert captured_value != DEV_OTP, "Le hash ne doit jamais être égal à l'OTP en clair"
    assert len(captured_value) == 64, "SHA-256 produit 64 caractères hexadécimaux"


@pytest.mark.asyncio
async def test_verify_otp_with_correct_hash_succeeds(auth_service):
    """verify_otp réussit quand get_otp retourne sha256(otp_correct)."""
    phone = "+25779000002"

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
    """verify_otp échoue quand le hash de l'OTP soumis ne correspond pas au hash stocké."""
    from fastapi import HTTPException

    # Stocké : hash de "654321" — soumis : "000000"
    wrong_hash = hashlib.sha256("654321".encode()).hexdigest()

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
    """DEV_OTP '123456' fonctionne toujours en mode development via le hash."""
    phone = "+25779000004"

    # Simuler ce que save_otp stocke : le hash du DEV_OTP
    with patch("app.services.auth_service.get_otp", new_callable=AsyncMock, return_value=DEV_OTP_HASH):
        with patch("app.services.auth_service.increment_otp_attempts", new_callable=AsyncMock, return_value=1):
            with patch("app.services.auth_service.delete_otp", new_callable=AsyncMock):
                result = await auth_service.verify_otp(
                    VerifyOtpRequest(phone=phone, otp="123456")
                )

    assert result.access_token is not None
    assert result.user.is_verified is True


@pytest.mark.asyncio
async def test_hash_otp_deterministic_and_64_chars():
    """_hash_otp produit toujours 64 caractères hex et est déterministe."""
    from app.core.redis import _hash_otp

    h1 = _hash_otp("123456")
    h2 = _hash_otp("123456")

    assert h1 == h2, "_hash_otp doit être déterministe"
    assert len(h1) == 64, "SHA-256 produit 64 caractères hexadécimaux"
    assert h1 != "123456", "Le hash ne doit jamais être égal à l'entrée"
    # Deux OTP différents produisent des hash différents
    assert _hash_otp("123456") != _hash_otp("654321")


# ── TASK-02 : tests Refresh Token persisté en base ───────────────────────────

@pytest.mark.asyncio
async def test_login_persists_refresh_token_in_db(auth_service, db_session):
    """Après login, un enregistrement RefreshToken existe en base."""
    from sqlalchemy import select as sa_select
    from app.models.refresh_token import RefreshToken

    result = await auth_service.register_email(
        RegisterEmailRequest(email="persist@test.bi", password="Pass1234", name="Test")
    )

    # Vérifier qu'un RefreshToken existe en DB pour cet utilisateur
    rt_result = await db_session.execute(
        sa_select(RefreshToken).where(RefreshToken.user_id == result.user.id)
    )
    record = rt_result.scalar_one_or_none()

    assert record is not None
    assert record.revoked_at is None   # session active
    assert record.token_hash != result.refresh_token  # hash, pas le clair
    assert len(record.token_hash) == 64  # SHA-256 = 64 hex chars


@pytest.mark.asyncio
async def test_token_stored_as_hash_not_plaintext(auth_service, db_session):
    """Le token_hash en DB est sha256(refresh_token), jamais le token brut."""
    import hashlib
    from sqlalchemy import select as sa_select
    from app.models.refresh_token import RefreshToken

    result = await auth_service.register_email(
        RegisterEmailRequest(email="hash@test.bi", password="Pass1234", name="Hash")
    )

    rt_result = await db_session.execute(
        sa_select(RefreshToken).where(RefreshToken.user_id == result.user.id)
    )
    record = rt_result.scalar_one()

    expected_hash = hashlib.sha256(result.refresh_token.encode()).hexdigest()
    assert record.token_hash == expected_hash


@pytest.mark.asyncio
async def test_logout_revokes_token(auth_service, db_session):
    """POST /logout révoque le refresh token — revoked_at devient non-NULL."""
    from sqlalchemy import select as sa_select
    from app.models.refresh_token import RefreshToken

    result = await auth_service.register_email(
        RegisterEmailRequest(email="logout@test.bi", password="Pass1234", name="Logout")
    )
    refresh_token_str = result.refresh_token

    # Vérifier session active avant logout
    rt_result = await db_session.execute(
        sa_select(RefreshToken).where(RefreshToken.user_id == result.user.id)
    )
    record = rt_result.scalar_one()
    assert record.revoked_at is None

    # Logout
    logout_result = await auth_service.logout(refresh_token_str)
    assert logout_result["success"] is True

    # Vérifier session révoquée
    await db_session.refresh(record)
    assert record.revoked_at is not None


@pytest.mark.asyncio
async def test_revoked_token_rejected_on_refresh(auth_service):
    """Un token révoqué est rejeté par POST /refresh → HTTP 401 TOKEN_REVOKED."""
    from fastapi import HTTPException

    result = await auth_service.register_email(
        RegisterEmailRequest(email="revoked@test.bi", password="Pass1234", name="Revoked")
    )
    refresh_token_str = result.refresh_token

    # Révoquer
    await auth_service.logout(refresh_token_str)

    # Tenter de rafraîchir avec le token révoqué
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.refresh_token(refresh_token_str)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "TOKEN_REVOKED"


@pytest.mark.asyncio
async def test_rotation_invalidates_old_token(auth_service, db_session):
    """Après rotation, l'ancien token est révoqué et un nouveau token est créé."""
    from sqlalchemy import select as sa_select
    from app.models.refresh_token import RefreshToken

    result = await auth_service.register_email(
        RegisterEmailRequest(email="rotation@test.bi", password="Pass1234", name="Rotation")
    )
    old_token = result.refresh_token

    # Rotation
    new_result = await auth_service.refresh_token(old_token)

    assert new_result.refresh_token != old_token
    assert new_result.access_token is not None

    # L'ancien token doit être révoqué
    import hashlib
    old_hash = hashlib.sha256(old_token.encode()).hexdigest()
    rt_result = await db_session.execute(
        sa_select(RefreshToken).where(RefreshToken.token_hash == old_hash)
    )
    old_record = rt_result.scalar_one()
    assert old_record.revoked_at is not None

    # Un nouveau token doit exister
    new_hash = hashlib.sha256(new_result.refresh_token.encode()).hexdigest()
    new_rt = await db_session.execute(
        sa_select(RefreshToken).where(RefreshToken.token_hash == new_hash)
    )
    new_record = new_rt.scalar_one()
    assert new_record.revoked_at is None


@pytest.mark.asyncio
async def test_logout_all_revokes_all_sessions(auth_service, db_session):
    """logout_all révoque toutes les sessions — sessions_revoked = N."""
    from sqlalchemy import select as sa_select
    from app.models.refresh_token import RefreshToken

    # Créer 3 sessions (register + 2 logins)
    result1 = await auth_service.register_email(
        RegisterEmailRequest(email="all@test.bi", password="Pass1234", name="All")
    )
    user_id = result1.user.id

    result2 = await auth_service.login_email(
        LoginEmailRequest(email="all@test.bi", password="Pass1234")
    )
    result3 = await auth_service.login_email(
        LoginEmailRequest(email="all@test.bi", password="Pass1234")
    )

    # Vérifier 3 sessions actives
    rt_result = await db_session.execute(
        sa_select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    assert len(rt_result.scalars().all()) == 3

    # Logout all
    logout_result = await auth_service.logout_all(user_id)

    assert logout_result["success"] is True
    assert logout_result["sessions_revoked"] == 3

    # Vérifier 0 sessions actives
    rt_result2 = await db_session.execute(
        sa_select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    assert len(rt_result2.scalars().all()) == 0


@pytest.mark.asyncio
async def test_multi_device_independent_sessions(auth_service, db_session):
    """Deux devices ont des sessions indépendantes — logout d'un ne touche pas l'autre."""
    from sqlalchemy import select as sa_select
    from app.models.refresh_token import RefreshToken

    email = "multidevice@test.bi"
    await auth_service.register_email(
        RegisterEmailRequest(email=email, password="Pass1234", name="Multi")
    )

    # Login device phone
    phone_result = await auth_service.login_email(
        LoginEmailRequest(email=email, password="Pass1234", device_id="phone")
    )
    # Login device tablet
    tablet_result = await auth_service.login_email(
        LoginEmailRequest(email=email, password="Pass1234", device_id="tablet")
    )

    # Logout phone uniquement
    await auth_service.logout(phone_result.refresh_token)

    # La session tablet doit rester active
    import hashlib
    tablet_hash = hashlib.sha256(tablet_result.refresh_token.encode()).hexdigest()
    rt = await db_session.execute(
        sa_select(RefreshToken).where(RefreshToken.token_hash == tablet_hash)
    )
    tablet_record = rt.scalar_one()
    assert tablet_record.revoked_at is None, "La session tablet ne doit pas être révoquée"


@pytest.mark.asyncio
async def test_token_not_in_db_rejected(auth_service):
    """Un JWT valide non enregistré en base est rejeté → HTTP 401."""
    from fastapi import HTTPException
    from app.core.security import create_refresh_token

    # Générer un JWT valide sans l'insérer en DB
    fake_jwt = create_refresh_token("fake-user-id-not-in-db")

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.refresh_token(fake_jwt)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "INVALID_REFRESH_TOKEN"
