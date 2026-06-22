# Implementation Plan — TASK-06 : Rate Limiting

## Overview

1 nouveau fichier (`middlewares.py`) + 3 fichiers modifiés (`main.py`, `auth.py`, `tickets.py`).
Aucune migration, aucune nouvelle dépendance — `slowapi==0.1.9` est déjà dans `requirements.txt`.

Branche Git : `feat/rate-limiting`

---

## Tasks

- [ ] 1. Créer `app/core/middlewares.py`
  - Importer `Limiter`, `_rate_limit_exceeded_handler` depuis `slowapi`
  - Importer `get_remote_address` depuis `slowapi.util`
  - Importer `RateLimitExceeded` depuis `slowapi.errors`
  - Importer `FastAPI` depuis `fastapi`
  - Créer l'instance globale : `limiter = Limiter(key_func=get_remote_address)`
  - Créer la fonction `setup_rate_limiting(app: FastAPI) -> None` avec docstring
    - `app.state.limiter = limiter`
    - `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)`
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] 2. Brancher `setup_rate_limiting` dans `app/main.py`
  - Ajouter l'import : `from app.core.middlewares import setup_rate_limiting`
  - Appeler `setup_rate_limiting(app)` immédiatement après `app = FastAPI(...)` et avant `app.add_middleware(...)`
  - _Requirements: 1.4, 1.5_

- [ ] 3. Protéger les 4 endpoints dans `app/routers/auth.py`
  - Ajouter les imports en tête :
    ```python
    from fastapi import Request
    from app.core.middlewares import limiter
    ```
  - [ ] 3.1 `POST /register/phone` — ajouter `@limiter.limit("5/minute")` + `request: Request` en 1er paramètre
  - [ ] 3.2 `POST /verify-otp` — ajouter `@limiter.limit("5/minute")` + `request: Request` en 1er paramètre
  - [ ] 3.3 `POST /login` — ajouter `@limiter.limit("10/minute")` + `request: Request` en 1er paramètre
  - [ ] 3.4 `POST /refresh` — ajouter `@limiter.limit("20/minute")` + `request: Request` en 1er paramètre
  - Vérifier que `request: Request` est **le premier paramètre** de chaque handler (obligatoire pour slowapi)
  - _Requirements: 2.1, 3.1, 4.1, 5.1, 7.1_

- [ ] 4. Protéger les 2 endpoints WebSocket dans `app/routers/tickets.py`
  - Ajouter l'import : `from app.core.middlewares import limiter`
  - [ ] 4.1 `@router.websocket("/ws/queue/{ticket_id}")` — ajouter `@limiter.limit("10/minute")`
  - [ ] 4.2 `@router.websocket("/ws/counter/{counter_id}")` — ajouter `@limiter.limit("10/minute")`
  - Vérifier que `websocket: WebSocket` reste le premier paramètre (slowapi accepte WebSocket)
  - _Requirements: 6.1, 6.2, 7.2_

- [ ] 5. Checkpoint — démarrage de l'app sans erreur
  - Lancer `uvicorn app.main:app --reload` et vérifier que l'app démarre
  - Vérifier que `/docs` charge correctement (les décorateurs slowapi ne cassent pas OpenAPI)
  - Tester manuellement un endpoint protégé : 1 requête → réponse normale (pas de 429)

- [ ] 6. Écrire les tests dans `tests/test_rate_limiting.py` (nouveau fichier)
  - Créer les fixtures `test_app` et `client` (voir design.md — Testing Strategy)
  - [ ] 6.1 `test_login_allows_under_limit`
    - Envoyer 10 requêtes `POST /api/v1/auth/login` → toutes doivent retourner HTTP 401 (pas 429)
    - _Requirements: 2.4_
  - [ ] 6.2 `test_login_rate_limit_returns_429_after_threshold`
    - Envoyer 11 requêtes → la 11ème doit retourner HTTP 429
    - _Requirements: 2.2_
  - [ ] 6.3 `test_429_response_has_retry_after_header`
    - Déclencher un 429 → vérifier que `response.headers["Retry-After"]` existe et est un entier positif
    - _Requirements: 2.3, 8.2_
  - [ ] 6.4 `test_otp_rate_limit_after_5_attempts`
    - Envoyer 6 requêtes `POST /api/v1/auth/verify-otp` → la 6ème doit retourner HTTP 429
    - _Requirements: 4.2_
  - [ ] 6.5 `test_register_phone_rate_limit`
    - Envoyer 6 requêtes `POST /api/v1/auth/register/phone` → la 6ème doit retourner HTTP 429
    - _Requirements: 3.2_

- [ ] 7. Checkpoint final — tous les tests au vert
  - Lancer `pytest tests/ -v --tb=short`
  - Vérifier que les tests existants (auth, ticket, agency, organization) ne sont pas cassés
  - Vérifier que les 5 nouveaux tests passent

## Notes

- `request: Request` doit être importé depuis `fastapi`, pas autre chose
- L'ordre des décorateurs est important : `@router.post(...)` en premier, puis `@limiter.limit(...)` en dessous
- Si les tests existants échouent à cause de `request: Request` manquant dans les mocks, les tests unitaires existants n'utilisent pas le router (ils appellent le service directement) — ils ne sont pas impactés
- Les tests de rate limiting nécessitent `TestClient` (synchrone) et non `AsyncClient` car ils testent la couche ASGI complète
- Avant de commencer : `git checkout main && git pull && git checkout -b feat/rate-limiting`
