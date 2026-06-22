# TONDE — Sprint 1 Backend

> Référence de l'équipe pour le Sprint 1.
> 3 développeurs backend + Vital (Tech Lead / Reviewer).
> Aucun push direct sur `main` — tout passe par Pull Request.

---

## Équipe Backend

| Rôle | Responsabilité |
|---|---|
| **Vital** | Tech Lead, Architecture, Code Review, Merge |
| **Dev 1** | À assigner sur les tâches ci-dessous |
| **Dev 2** | À assigner sur les tâches ci-dessous |
| **Dev 3** | À assigner sur les tâches ci-dessous |

Coordination : Notion (tâches) + WhatsApp (communication rapide) + GitHub PR (code).

---

## Objectif du Sprint 1

Consolider les fondations du backend : sécurité, scalabilité temps réel, et correction des règles métier critiques. Aucune nouvelle fonctionnalité — que des corrections et améliorations structurelles.

---

## Tâches Sprint 1

### TASK-01 — Sécurité OTP : hashage SHA-256

**Priorité :** 🔴 Critique — à faire en premier  
**Branche :** `fix/otp-hash-redis`  
**Décision de référence :** DÉCISION 2 (decisions.md)

**Problème actuel :** L'OTP est stocké en clair dans Redis. Faille de sécurité.

**Fichiers à modifier :**
- `app/core/redis.py` — `save_otp()` et `get_otp()`
- `app/services/auth_service.py` — `verify_otp()`

**Changement clé :**
```python
import hashlib

# Dans save_otp() — stocker le hash, jamais le clair
await r.setex(f"tonde:otp:{phone}", expire_seconds, hashlib.sha256(otp.encode()).hexdigest())

# Dans verify_otp() — comparer les hash
if hashlib.sha256(otp.encode()).hexdigest() != stored_otp:
    raise HTTPException(400, ...)
```

**Tests à écrire :**
- `test_otp_stored_as_hash_not_plaintext`
- `test_verify_otp_with_correct_hash_succeeds`
- `test_verify_otp_with_wrong_code_fails`

**Checklist PR :**
- [ ] `save_otp()` stocke SHA-256
- [ ] `verify_otp()` compare les hash
- [ ] L'OTP DEV `123456` fonctionne toujours en `ENVIRONMENT=development`
- [ ] Tests passent

---

### TASK-02 — Refresh Token persisté en base

**Priorité :** 🔴 Haute  
**Branche :** `feat/refresh-token-db`  
**Décision de référence :** DÉCISION 3 (decisions.md)

**Problème actuel :** Refresh token stateless — impossible de révoquer une session.

**Fichiers à créer :**
- `app/models/refresh_token.py` — nouveau modèle SQLAlchemy

**Fichiers à modifier :**
- `app/services/auth_service.py` — persister + révoquer + rotation
- `app/schemas/auth.py` — `LogoutRequest`
- `app/routers/auth.py` — endpoints `logout` et `logout/all`
- Migration Alembic : `alembic revision --autogenerate -m "add_refresh_tokens_table"`

**Endpoints à créer :**
```
POST /api/v1/auth/logout        → révoque le refresh token
POST /api/v1/auth/logout/all    → révoque tous les tokens du user
```

**Tests à écrire :**
- `test_logout_revokes_token`
- `test_revoked_token_rejected_on_refresh`
- `test_rotation_invalidates_old_token`
- `test_multi_device_independent_sessions`

**Checklist PR :**
- [ ] Modèle `RefreshToken` créé avec tous les champs
- [ ] Migration Alembic générée et testée
- [ ] Rotation token à chaque `POST /refresh`
- [ ] `POST /logout` révoque correctement
- [ ] Tests passent

---

### TASK-03 — Règle "1 ticket actif global"

**Priorité :** 🟠 Haute  
**Branche :** `fix/one-active-ticket-global`  
**Décision de référence :** DÉCISION 1 (decisions.md)

**Problème actuel :** La vérification filtre par `agency_id` — un user peut avoir des tickets dans plusieurs agences.

**Fichiers à modifier :**
- `app/services/ticket_service.py` — `_get_active_ticket()` et `create_ticket()`

**Changement clé :**
```python
# SUPPRIMER le filtre agency_id
# AJOUTER les statuts ABSENT, TRANSFERRED, INCOMPLETE dans la vérification

ACTIVE_STATUSES = [
    TicketStatus.WAITING,
    TicketStatus.CALLED,
    TicketStatus.SERVING,
    TicketStatus.ABSENT,
    TicketStatus.TRANSFERRED,
    TicketStatus.INCOMPLETE,
]

async def _get_active_ticket(self, user_id: str) -> Ticket | None:
    result = await self.db.execute(
        select(Ticket).where(
            Ticket.user_id == user_id,
            Ticket.status.in_(ACTIVE_STATUSES),
        )
    )
    return result.scalar_one_or_none()
```

**Réponse 409 améliorée** : inclure `active_ticket_id` et `active_ticket_number`.

**Tests à écrire :**
- `test_one_active_ticket_global_rule`
- `test_ticket_blocked_different_agency`
- `test_ticket_allowed_after_done`
- `test_ticket_allowed_after_cancel`
- `test_absent_ticket_blocks_new_ticket`
- `test_409_includes_active_ticket_id`

**Checklist PR :**
- [ ] Filtre `agency_id` supprimé de `_get_active_ticket()`
- [ ] `ACTIVE_STATUSES` inclut ABSENT, TRANSFERRED, INCOMPLETE
- [ ] Réponse 409 inclut `active_ticket_id`
- [ ] Tests passent

---

### TASK-04 — Clés Redis segmentées par service

**Priorité :** 🟠 Haute  
**Branche :** `feat/redis-queue-key-by-service`  
**Décision de référence :** DÉCISION 4 (decisions.md)

**Problème actuel :** Clé `tonde:{org}:{agency}:queue` — une seule file par agence, pas extensible.

**Fichiers à modifier :**
- `app/core/redis.py` — `_queue_key()` + toutes les fonctions de file
- `app/services/ticket_service.py` — passer `service_id` à chaque appel Redis
- `app/schemas/ticket.py` — ajouter `service_id` dans `CallNextRequest`
- `app/routers/tickets.py` — passer `service_id` dans `call_next`

**Changement clé :**
```python
# AVANT
def _queue_key(org_id: str, agency_id: str) -> str:
    return f"tonde:{org_id}:{agency_id}:queue"

# APRÈS
def _queue_key(org_id: str, agency_id: str, service_id: str) -> str:
    return f"tonde:{org_id}:{agency_id}:{service_id}:queue"
```

**Tests à écrire :**
- `test_queue_key_includes_service_id`
- `test_two_services_independent_queues`
- `test_call_next_targets_correct_service`

**Checklist PR :**
- [ ] `_queue_key()` inclut `service_id`
- [ ] Toutes les fonctions Redis de file mises à jour
- [ ] `CallNextRequest` inclut `service_id`
- [ ] Tests passent

---

### TASK-05 — Redis Pub/Sub activé

**Priorité :** 🟡 Moyenne  
**Branche :** `feat/redis-pubsub-listener`  
**Décision de référence :** DÉCISION 5 (decisions.md)

**Problème actuel :** `start_redis_listener()` existe mais n'est pas branché dans `main.py`.

**Fichiers à modifier :**
- `app/websocket/queue_ws.py` — améliorer `start_redis_listener()` avec `psubscribe` + reconnexion automatique
- `app/main.py` — `asyncio.create_task(ws_manager.start_redis_listener())` dans `lifespan()`

**Reconnexion automatique :**
```python
async def start_redis_listener(self) -> None:
    while True:
        try:
            r = await get_redis()
            async with r.pubsub() as pubsub:
                await pubsub.psubscribe("tonde:events:*")
                async for message in pubsub.listen():
                    ...
        except Exception as e:
            logger.error(f"Redis Pub/Sub déconnecté: {e}. Reconnexion dans 5s...")
            await asyncio.sleep(5)
```

**Tests à écrire :**
- `test_event_published_dispatched_to_correct_client`
- `test_listener_handles_unknown_event_gracefully`

**Checklist PR :**
- [ ] Listener branché dans `lifespan()`
- [ ] Reconnexion automatique implémentée
- [ ] `psubscribe("tonde:events:*")` utilisé
- [ ] Tests passent

---

### TASK-06 — Rate Limiting

**Priorité :** 🟡 Moyenne  
**Branche :** `feat/rate-limiting`  
**Décision de référence :** DÉCISION 6 (decisions.md)

**Problème actuel :** `slowapi` est dans `requirements.txt` mais pas branché.

**Fichiers à créer :**
- `app/core/middlewares.py` — `Limiter` + `setup_rate_limiting()`

**Fichiers à modifier :**
- `app/main.py` — appeler `setup_rate_limiting(app)`
- `app/routers/auth.py` — décorateurs `@limiter.limit(...)`

**Tests à écrire :**
- `test_login_rate_limit_returns_429_after_threshold`
- `test_otp_rate_limit_after_5_attempts`

**Checklist PR :**
- [ ] `middlewares.py` créé
- [ ] 5 endpoints protégés (voir DÉCISION 6)
- [ ] HTTP 429 avec header `Retry-After`
- [ ] Tests passent

---

## Règles Git pour ce Sprint

```bash
# Démarrer une tâche
git checkout main && git pull origin main
git checkout -b fix/otp-hash-redis   # adapter selon la tâche

# Avant chaque PR
docker-compose exec api pytest --tb=short -q

# Nommage des commits
fix: stocker OTP hashé SHA-256 dans Redis
feat: table refresh_tokens et endpoints logout
fix: règle 1 ticket actif global sans filtre agence
feat: clés Redis segmentées par service_id
feat: activer Redis Pub/Sub listener dans lifespan
feat: rate limiting sur endpoints auth critiques
```

**Vital merge tout. Personne ne merge soi-même.**

---

## Ordre d'exécution recommandé

```
TASK-01 (OTP hash)         ← sécurité, faire en premier
TASK-02 (Refresh Token)    ← auth, peut être parallèle avec TASK-03
TASK-03 (1 ticket global)  ← règle métier critique
TASK-04 (Clés Redis)       ← avant tout nouveau test de queue
TASK-05 (Pub/Sub)          ← après TASK-04
TASK-06 (Rate Limiting)    ← peut être fait en parallèle
```
