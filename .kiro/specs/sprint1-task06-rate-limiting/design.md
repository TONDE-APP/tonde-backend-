# Design Document — TASK-06 : Rate Limiting

## Overview

Brancher `slowapi==0.1.9` (déjà dans `requirements.txt`) sur 6 endpoints critiques.
Surface de changement : 1 nouveau fichier (`middlewares.py`), 3 fichiers modifiés (`main.py`, `routers/auth.py`, `routers/tickets.py`).
Aucune migration, aucun nouveau modèle.

---

## Architecture

`slowapi` fonctionne en deux temps :

1. Une instance `Limiter` est créée avec une fonction de clé (`get_remote_address` → IP du client).
2. Chaque handler décoré avec `@limiter.limit("N/minute")` est intercepté avant exécution. Si la limite est dépassée, `slowapi` lève `RateLimitExceeded` — un handler d'exception enregistré sur l'app FastAPI retourne HTTP 429 automatiquement.

```
Client HTTP
    │
    ▼
FastAPI middleware
    │
    ▼
@limiter.limit("10/minute")   ← vérifie le compteur Redis/mémoire
    │
    ├── sous le seuil → handler exécuté normalement
    └── dépassement → RateLimitExceeded → handler 429 → HTTP 429 + Retry-After
```

---

## Components and Interfaces

### 1. `app/core/middlewares.py` (nouveau fichier)

```python
"""
Middlewares TONDE — Rate Limiting via slowapi.

Usage dans un router :
    from app.core.middlewares import limiter
    from fastapi import Request

    @router.post("/login")
    @limiter.limit("10/minute")
    async def login(request: Request, body: LoginEmailRequest, ...):
        ...
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI


# Instance globale partagée par tous les routers
limiter = Limiter(key_func=get_remote_address)


def setup_rate_limiting(app: FastAPI) -> None:
    """
    Attache le rate limiter à l'instance FastAPI.
    Doit être appelée dans main.py avant le démarrage de l'app.

    Args:
        app: Instance FastAPI à protéger
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

### 2. `app/main.py` — ajout de `setup_rate_limiting`

Ajouter l'import et l'appel **avant** `lifespan` :

```python
from app.core.middlewares import setup_rate_limiting

# Après la création de app = FastAPI(...) et avant app.add_middleware(CORSMiddleware, ...)
setup_rate_limiting(app)
```

L'ordre d'appel est important : `setup_rate_limiting` doit être appelée **après** la création de l'instance `app` et **avant** le premier appel à `include_router`.

### 3. `app/routers/auth.py` — décorateurs sur 4 endpoints

**Import à ajouter :**
```python
from fastapi import Request
from app.core.middlewares import limiter
```

**Endpoints protégés :**

| Endpoint | Décorateur | Paramètre ajouté |
|---|---|---|
| `POST /register/phone` | `@limiter.limit("5/minute")` | `request: Request` en 1er |
| `POST /verify-otp` | `@limiter.limit("5/minute")` | `request: Request` en 1er |
| `POST /login` | `@limiter.limit("10/minute")` | `request: Request` en 1er |
| `POST /refresh` | `@limiter.limit("20/minute")` | `request: Request` en 1er |

**Exemple exact après modification :**

```python
@router.post("/login", summary="Connexion par email + mot de passe")
@limiter.limit("10/minute")
async def login_email(
    request: Request,          # ← OBLIGATOIRE en premier (requis par slowapi)
    body: LoginEmailRequest,
    db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    return await service.login_email(body)
```

### 4. `app/routers/tickets.py` — décorateurs sur 2 endpoints WebSocket

**Import à ajouter :**
```python
from app.core.middlewares import limiter
```

Les endpoints WebSocket utilisent `WebSocket` comme premier paramètre — `slowapi` accepte `WebSocket` à la place de `Request` pour les handlers WebSocket.

```python
@router.websocket("/ws/queue/{ticket_id}")
@limiter.limit("10/minute")
async def websocket_queue(
    websocket: WebSocket,      # ← WebSocket accepté par slowapi à la place de Request
    ticket_id: str,
    ...
):
```

```python
@router.websocket("/ws/counter/{counter_id}")
@limiter.limit("10/minute")
async def websocket_counter(
    websocket: WebSocket,
    counter_id: str,
    ...
):
```

---

## Data Models

Aucun changement de modèle. `slowapi` maintient ses compteurs en mémoire par défaut. Pour un déploiement multi-instance, les compteurs doivent être partagés via Redis — mais pour le MVP avec une seule instance, la mémoire est suffisante.

> Note pour Vital : si TONDE scale sur 2+ instances derrière un load balancer, configurer `slowapi` avec un backend Redis : `Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)`. Ce changement est à faire au moment du passage en multi-instance, pas maintenant.

---

## Correctness Properties

### Property 1 : Limite respectée par IP

*Pour toute* IP et tout endpoint protégé, les N premières requêtes dans la fenêtre d'1 minute doivent retourner le code HTTP normal. La (N+1)ème doit retourner HTTP 429.

**Validates: Requirements 2.2, 3.2, 4.2, 5.2, 6.3**

### Property 2 : Header Retry-After présent

*Pour toute* réponse HTTP 429 émise par le rate limiter, le header `Retry-After` doit être présent et contenir une valeur entière positive.

**Validates: Requirements 2.3, 8.2**

---

## Error Handling

| Situation | Comportement attendu |
|---|---|
| IP dépasse la limite | HTTP 429 + header `Retry-After` + body JSON avec message |
| `request: Request` absent du handler | Erreur de configuration levée par `slowapi` au démarrage |
| `setup_rate_limiting()` non appelée | Pas de protection — les décorateurs sont ignorés silencieusement |
| Redis indisponible (futur backend Redis) | Fallback mémoire — comportement dégradé acceptable pour MVP |

**Format de la réponse 429 produite par `_rate_limit_exceeded_handler` :**
```json
{"error": "Rate limit exceeded: 10 per 1 minute"}
```

Ce format est généré automatiquement par `slowapi`. Le mobile doit lire le header `Retry-After` pour savoir quand réessayer.

---

## Testing Strategy

### Approche

Les tests de rate limiting utilisent le `TestClient` de FastAPI (synchrone) car `slowapi` fonctionne au niveau ASGI — les tests doivent passer par la stack HTTP complète, pas directement les services.

### Fixtures nécessaires

```python
@pytest.fixture
def test_app():
    """App FastAPI de test avec rate limiting activé."""
    from fastapi import FastAPI
    from app.core.middlewares import setup_rate_limiting
    from app.routers.auth import router as auth_router

    app = FastAPI()
    setup_rate_limiting(app)
    app.include_router(auth_router, prefix="/api/v1/auth")
    return app

@pytest.fixture
def client(test_app):
    from fastapi.testclient import TestClient
    return TestClient(test_app)
```

### Tests à écrire dans `tests/test_rate_limiting.py`

| Test | Scénario | Attendu |
|---|---|---|
| `test_login_allows_under_limit` | 10 requêtes sur `/login` | Toutes HTTP 401 (mauvais creds, mais pas 429) |
| `test_login_rate_limit_returns_429_after_threshold` | 11ème requête sur `/login` | HTTP 429 |
| `test_429_response_has_retry_after_header` | Dépassement limite | Header `Retry-After` présent |
| `test_otp_rate_limit_after_5_attempts` | 6ème requête sur `/verify-otp` | HTTP 429 |
| `test_register_phone_rate_limit` | 6ème requête sur `/register/phone` | HTTP 429 |
| `test_different_ips_have_independent_counters` | 11 req IP_A + 1 req IP_B | IP_A → 429, IP_B → normal |
