"""
Middlewares TONDE — Rate Limiting via slowapi.

Usage dans un router :
    from fastapi import Request
    from app.core.middlewares import limiter

    @router.post("/login")
    @limiter.limit("10/minute")
    async def login(request: Request, body: LoginEmailRequest, ...):
        ...

Note : request: Request doit être le PREMIER paramètre de chaque handler protégé.
C'est une contrainte de slowapi — il lit l'IP depuis l'objet Request.
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI


# Instance globale partagée par tous les routers.
# key_func=get_remote_address → limite par adresse IP cliente.
limiter = Limiter(key_func=get_remote_address)


def setup_rate_limiting(app: FastAPI) -> None:
    """
    Attache le rate limiter à l'instance FastAPI.
    Doit être appelée dans main.py après la création de l'app,
    avant app.add_middleware() et app.include_router().

    Args:
        app: Instance FastAPI à protéger
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
