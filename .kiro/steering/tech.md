# TONDE — Stack Technique

## Backend

| Composant | Choix | Version |
|-----------|-------|---------|
| Framework | FastAPI | 0.111.0 |
| Runtime | Python | 3.12+ |
| Serveur ASGI | Uvicorn | 0.30.1 |
| ORM | SQLAlchemy (async) | 2.0.30 |
| Migrations | Alembic | 1.13.1 |
| Validation | Pydantic v2 | 2.7.1 |
| Base de données | PostgreSQL | 15 |
| Driver async DB | asyncpg | 0.29.0 |
| Cache / File | Redis | 7 |
| Auth | JWT via python-jose | 3.3.0 |
| Hachage | passlib bcrypt | 1.7.4 |
| WebSocket | websockets | 12.0 |
| SMS (Afrique) | Africa's Talking | 1.2.5 |
| Push notifs | Firebase FCM via httpx | — |
| QR Code | qrcode | 7.4.2 |
| Images | Pillow | 10.3.0 |

## Déploiement

- Docker + Docker Compose (orchestration locale et VPS)
- VPS Linux
- GitHub Actions (CI/CD)

## Architecture

- **Monolithique modulaire** — jamais de microservices sur le MVP
- **Async partout** — SQLAlchemy async, asyncpg, Redis async
- Pool de connexions DB : `pool_size=10`, `max_overflow=20`
- Temps réel : FastAPI + Redis Pub/Sub + WebSocket Connection Manager

## Authentification

- Access Token JWT : 15 minutes
- Refresh Token JWT : 7 jours (configurable jusqu'à 30 jours)
- OTP SMS via Africa's Talking (code fixe `123456` en développement)
- RBAC : `client` | `agent` | `manager` | `admin`
- Futures évolutions prévues : OAuth Google, OAuth Facebook

## Objectifs de performance

| Métrique | Cible |
|----------|-------|
| API P99 | < 200 ms |
| WebSocket P50 | < 100 ms |
| WebSocket P99 | < 300 ms |
| Uptime | > 99.5 % |

## Variables d'environnement clés

Toutes lues depuis `.env` via `pydantic-settings` dans `app/core/config.py` :

```
DATABASE_URL          # postgresql+asyncpg://...
REDIS_URL             # redis://...
JWT_SECRET_KEY
ENVIRONMENT           # development | production
AFRICAS_TALKING_USERNAME / API_KEY
FIREBASE_SERVER_KEY
ALLOWED_ORIGINS
```

## Commandes courantes

```bash
# Lancer l'environnement complet (API + PostgreSQL + Redis)
docker-compose up

# Lancer uniquement l'API en local (hors Docker)
uvicorn app.main:app --reload --port 8000

# Créer une migration Alembic
alembic revision --autogenerate -m "description"

# Appliquer les migrations
alembic upgrade head

# Lancer les tests
pytest
pytest -v                        # verbose
pytest tests/test_auth.py        # fichier spécifique
pytest-asyncio                   # pour les tests async

# Accès interfaces
# Swagger  : http://localhost:8000/docs
# ReDoc    : http://localhost:8000/redoc
# Health   : http://localhost:8000/health
# Redis UI : http://localhost:8081
```

## Multi-tenant — règle absolue

Toutes les entités métier doivent inclure `org_id` ou `tenant_id`. La sécurité doit être compatible avec PostgreSQL Row Level Security (RLS). Aucune fuite de données entre organisations n'est acceptable.

## Qualité attendue

- Code production-ready uniquement
- Typage complet (Pydantic v2, SQLAlchemy 2.0 `Mapped[]`)
- Docstrings utiles sur chaque fonction non triviale
- Tests unitaires pour toute logique métier
- Jamais de code temporaire ou jetable
