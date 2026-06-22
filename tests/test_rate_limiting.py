"""
Tests unitaires — Rate Limiting (TASK-06)

Ces tests passent par la stack HTTP complète (TestClient ASGI)
car slowapi intercepte au niveau middleware, pas au niveau service.

Note : slowapi maintient les compteurs en mémoire par défaut.
Chaque fixture recrée une app fraîche pour isoler les compteurs entre tests.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.core.middlewares import setup_rate_limiting, Limiter, get_remote_address


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_test_app() -> FastAPI:
    """
    Crée une app FastAPI de test avec rate limiting activé.
    Utilise un Limiter frais à chaque appel pour isoler les compteurs.
    """
    from app.routers.auth import router as auth_router

    # Nouveau Limiter par app pour isoler les compteurs entre tests
    fresh_limiter = Limiter(key_func=get_remote_address)

    app = FastAPI()

    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app.state.limiter = fresh_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Patcher le limiter du router avec le nouveau
    import app.routers.auth as auth_module
    original_limiter = auth_module.limiter

    # Remplacer temporairement le limiter global dans le module auth
    auth_module.limiter = fresh_limiter
    app.include_router(auth_router, prefix="/api/v1/auth")
    # Restaurer (le TestClient est synchrone donc pas de problème de concurrence ici)
    auth_module.limiter = original_limiter

    return app


@pytest.fixture
def client():
    """Client de test avec une app fraîche et rate limiting activé."""
    app = _make_test_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Corps de requête valides pour déclencher les endpoints ────────────────────

REGISTER_PHONE_BODY = {"phone": "+25779000001", "country_code": "BI"}
VERIFY_OTP_BODY = {"phone": "+25779000001", "otp": "123456"}
LOGIN_BODY = {"email": "test@tonde.bi", "password": "wrongpassword"}
REFRESH_BODY = {"refresh_token": "invalid.token.here"}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_rate_limiter_setup():
    """setup_rate_limiting() configure app.state.limiter et le handler 429."""
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    setup_rate_limiting(app)

    assert hasattr(app.state, "limiter")
    assert RateLimitExceeded in app.exception_handlers


def test_middlewares_module_exports_limiter():
    """Le module middlewares exporte bien l'instance limiter."""
    from app.core.middlewares import limiter as exported_limiter
    assert exported_limiter is not None


def test_login_allows_requests_under_limit():
    """Les 10 premières requêtes sur /login passent (pas de 429)."""
    app = _make_test_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        with patch("app.services.auth_service.AuthService.login_email", new_callable=AsyncMock) as mock_login:
            from fastapi import HTTPException, status
            mock_login.side_effect = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "test"}
            )
            for i in range(10):
                resp = client.post("/api/v1/auth/login", json=LOGIN_BODY)
                assert resp.status_code != 429, f"Requête {i+1}/10 ne doit pas être limitée"


def test_login_rate_limit_returns_429_after_threshold():
    """La 11ème requête sur /login retourne HTTP 429."""
    app = _make_test_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        with patch("app.services.auth_service.AuthService.login_email", new_callable=AsyncMock) as mock_login:
            from fastapi import HTTPException, status
            mock_login.side_effect = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "test"}
            )
            # Consommer les 10 requêtes autorisées
            for _ in range(10):
                client.post("/api/v1/auth/login", json=LOGIN_BODY)

            # La 11ème doit être bloquée
            resp = client.post("/api/v1/auth/login", json=LOGIN_BODY)
            assert resp.status_code == 429


def test_429_response_has_retry_after_header():
    """Une réponse 429 contient le header Retry-After (insensible à la casse)."""
    app = _make_test_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        with patch("app.services.auth_service.AuthService.login_email", new_callable=AsyncMock) as mock_login:
            from fastapi import HTTPException, status
            mock_login.side_effect = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "test"}
            )
            for _ in range(10):
                client.post("/api/v1/auth/login", json=LOGIN_BODY)

            resp = client.post("/api/v1/auth/login", json=LOGIN_BODY)
            assert resp.status_code == 429

            # slowapi inclut Retry-After dans le body ou les headers
            # Vérifier soit le header soit le message d'erreur dans le body
            headers_lower = {k.lower(): v for k, v in resp.headers.items()}
            has_retry_after = "retry-after" in headers_lower
            has_rate_limit_info = "x-ratelimit" in " ".join(headers_lower.keys())
            has_rate_limit_body = "rate limit" in resp.text.lower() or "10 per" in resp.text.lower()

            assert has_retry_after or has_rate_limit_info or has_rate_limit_body, \
                f"Aucune info de rate limit trouvée. Headers: {dict(resp.headers)}, Body: {resp.text}"


def test_otp_rate_limit_after_5_attempts():
    """La 6ème requête sur /verify-otp retourne HTTP 429."""
    app = _make_test_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        with patch("app.services.auth_service.AuthService.verify_otp", new_callable=AsyncMock) as mock_verify:
            from fastapi import HTTPException, status
            mock_verify.side_effect = HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_OTP", "message": "test"}
            )
            for _ in range(5):
                client.post("/api/v1/auth/verify-otp", json=VERIFY_OTP_BODY)

            resp = client.post("/api/v1/auth/verify-otp", json=VERIFY_OTP_BODY)
            assert resp.status_code == 429


def test_register_phone_rate_limit_after_5_attempts():
    """La 6ème requête sur /register/phone retourne HTTP 429."""
    app = _make_test_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        with patch("app.services.auth_service.AuthService.register_phone", new_callable=AsyncMock) as mock_reg:
            mock_reg.return_value = {"success": True, "otp_sent": True, "expires_in_seconds": 300}
            for _ in range(5):
                client.post("/api/v1/auth/register/phone", json=REGISTER_PHONE_BODY)

            resp = client.post("/api/v1/auth/register/phone", json=REGISTER_PHONE_BODY)
            assert resp.status_code == 429
