"""
Configuration centrale de TONDE Backend.
Toutes les variables d'environnement sont lues et validées ici.
Pydantic-settings garantit qu'une variable manquante fait crasher
l'app au démarrage plutôt qu'en cours d'exécution.
"""
import logging
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import List


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────
    APP_NAME: str = "Tonde API"
    APP_VERSION: str = "1.0.0"
    APP_PORT: int = 8000
    # Valeurs : development | staging | production
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # ── Base de données ───────────────────────────────────────
    DATABASE_URL: str

    # ── Migrations ────────────────────────────────────────────
    # True uniquement en développement pour créer les tables sans Alembic.
    # En production, toujours False — utiliser 'alembic upgrade head'.
    CREATE_TABLES_ON_STARTUP: bool = False

    # ── Redis ─────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

    # ── JWT ───────────────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── OTP ───────────────────────────────────────────────────
    AFRICAS_TALKING_USERNAME: str = "sandbox"
    AFRICAS_TALKING_API_KEY: str = ""
    AFRICAS_TALKING_SENDER_ID: str = "TONDE"
    OTP_EXPIRE_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 3

    # ── Firebase FCM ──────────────────────────────────────────
    FIREBASE_SERVER_KEY: str = ""

    # ── CORS ──────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    def get_allowed_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    def configure_logging(self) -> None:
        """Configure le logging structuré selon l'environnement."""
        level = logging.DEBUG if self.DEBUG else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",  # ignore HOST, PORT et toute variable .env non déclarée
    )


# Instance unique partagée dans tout le projet
settings = Settings()

# Configurer le logging dès l'import
settings.configure_logging()
