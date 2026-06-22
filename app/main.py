"""
TONDE BACKEND — Point d'entrée principal
========================================
Configure FastAPI, initialise les connexions et branche les routers.

En production : les migrations sont gérées par Alembic.
En développement : create_tables() peut créer les tables au démarrage
                   si CREATE_TABLES_ON_STARTUP=true dans .env.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.redis import get_redis, close_redis
from app.core.middlewares import setup_rate_limiting
from app.websocket.queue_ws import ws_manager

# Import explicite des modèles — obligatoire pour que Base.metadata
# connaisse toutes les tables avant toute opération DB
import app.models  # noqa: F401

from app.routers import auth, tickets, organizations, agencies, counters, employees

logger = logging.getLogger(__name__)


# ── Démarrage et arrêt de l'app ───────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code exécuté au démarrage et à l'arrêt de l'API.
    Initialise les connexions DB et Redis.

    En production, NE PAS utiliser create_tables().
    Utiliser : docker-compose exec api alembic upgrade head
    """
    listener_task: asyncio.Task | None = None

    logger.info("=" * 50)
    logger.info("TONDE API — Démarrage")
    logger.info(f"Environnement : {settings.ENVIRONMENT}")
    logger.info(f"Version       : {settings.APP_VERSION}")
    logger.info("=" * 50)

    try:
        # create_tables() uniquement en développement si flag activé
        if settings.CREATE_TABLES_ON_STARTUP:
            from app.core.database import create_tables
            await create_tables()
            logger.info("Base de données — Tables créées (mode dev)")
        else:
            logger.info("Base de données — Utiliser 'alembic upgrade head' pour les migrations")

        # Vérifier la connexion Redis
        redis = await get_redis()
        await redis.ping()
        logger.info("Redis — Connexion établie")

        # Démarrer le listener Redis Pub/Sub en tâche asyncio de fond
        # Reçoit les événements de toutes les orgs via psubscribe("tonde:events:*")
        listener_task = asyncio.create_task(ws_manager.start_redis_listener())
        app.state.redis_listener_task = listener_task
        logger.info("Redis Pub/Sub — Listener démarré en tâche de fond")

        logger.info(f"API prête sur http://localhost:{settings.APP_PORT}")
        logger.info(f"Documentation : http://localhost:{settings.APP_PORT}/docs")

        yield  # L'app tourne ici

    finally:
        if listener_task is not None:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                logger.info("Redis Pub/Sub — Listener arrêté")

        await close_redis()
        logger.info("TONDE API — Arrêt propre")


# ── Création de l'app FastAPI ─────────────────────────────────────────────────
app = FastAPI(
    title="Tonde API",
    description="""
## Tonde — Smart Queue Management System

API REST + WebSocket pour la gestion intelligente de file d'attente.

### Authentification
Utilisez le bouton **Authorize** ci-dessus et entrez : `Bearer <votre_token>`

### Environnement actuel
L'OTP de test en développement est toujours **123456**
    """,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Rate limiting — doit être appelé avant add_middleware et include_router
setup_rate_limiting(app)


# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(auth.router,          prefix="/api/v1/auth",          tags=["🔐 Auth"])
app.include_router(tickets.router,       prefix="/api/v1/tickets",       tags=["🎫 Tickets"])
app.include_router(organizations.router, prefix="/api/v1/organizations", tags=["🏢 Organizations"])
app.include_router(agencies.router,      prefix="/api/v1/organizations", tags=["🏦 Agencies"])
app.include_router(
    counters.router,
    prefix="/api/v1/organizations/{org_id}/agencies/{agency_id}/counters",
    tags=["🪟 Counters"],
)
app.include_router(
    employees.router,
    prefix="/api/v1/organizations/{org_id}/employees",
    tags=["👤 Employees"],
)


# ── Endpoints de base ─────────────────────────────────────────────────────────
@app.get("/", tags=["🏠 Accueil"])
async def root():
    return {
        "app": "Tonde API",
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health", tags=["🏠 Accueil"])
async def health_check():
    """
    Endpoint de santé — vérifié par Docker, load balancers et monitoring.
    Teste Redis et retourne un statut dégradé si un service est KO.
    """
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal

    # Test Redis
    redis_ok = False
    try:
        redis = await get_redis()
        await redis.ping()
        redis_ok = True
    except Exception as e:
        logger.warning(f"Health check Redis KO: {e}")

    # Test PostgreSQL
    db_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.warning(f"Health check DB KO: {e}")

    all_ok = redis_ok and db_ok

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "ok" if all_ok else "degraded",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "services": {
                "api": "ok",
                "redis": "ok" if redis_ok else "error",
                "database": "ok" if db_ok else "error",
            },
        },
    )


# ── Gestion globale des erreurs ───────────────────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": f"La route {request.url.path} n'existe pas",
            },
        },
    )


@app.exception_handler(500)
async def server_error_handler(request, exc):
    logger.error(f"Erreur 500 sur {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "SERVER_ERROR",
                "message": "Erreur interne du serveur. Contactez le support Tonde.",
            },
        },
    )
