"""
Connexion à la base de données PostgreSQL.
On utilise SQLAlchemy en mode asynchrone pour de meilleures performances.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


# ── Moteur de base de données ─────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,      # Affiche les requêtes SQL en mode debug
    pool_size=10,             # Nombre de connexions simultanées
    max_overflow=20,          # Connexions supplémentaires si besoin
)

# ── Fabrique de sessions ──────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── Classe de base pour tous les modèles ─────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dépendance FastAPI — injectée dans chaque route ──────────────────────────
async def get_db() -> AsyncSession:
    """
    Fournit une session DB à chaque requête API.
    La session est fermée automatiquement après la requête.

    Utilisation dans un router :
        async def mon_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Créer toutes les tables ───────────────────────────────────────────────────
async def create_tables():
    """Appelé au démarrage de l'app pour créer les tables si elles n'existent pas."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
