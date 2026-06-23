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

---

# TONDE — Sprint 2 Backend

> Sprint 2 : Multi-tenant avancé, Sécurité, Notifications, Analytics

## Objectif du Sprint 2

Finaliser les fondations du MVP avec :
- Support multi-organisation complet
- Notifications temps réel (SMS/FCM)
- Analytics de base
- Audit trail (Queue Logs)

---

## Tâches Sprint 2

### S2-01 — Renommage Agency → Branch

**Priorité :** 🔴 Critique — à merger en premier  
**Branche :** `feat/rename-agency-to-branch`  
**Décision de référence :** DÉCISION 8 (decisions.md)

**Fichiers à renommer :**
- `app/models/agency.py` → `app/models/branch.py`
- `app/schemas/agency.py` → `app/schemas/branch.py`
- `app/services/agency_service.py` → `app/services/branch_service.py`
- `app/routers/agencies.py` → `app/routers/branches.py`
- Migration Alembic : `ALTER TABLE agencies RENAME TO branches`

**Risque :** Breaking change — coordonner avec mobile avant merge

---

### S2-02 — Table user_organizations

**Priorité :** 🔴 Haute  
**Branche :** `feat/user-organizations-table`  
**Décision de référence :** DÉCISION 7 (decisions.md)

**Fichiers à créer :**
- `app/models/user_organization.py`
- Migration : `003_add_user_organizations_table.py`
- Tests : `test_user_organization.py`

---

### S2-03 — Refresh Token DB complet

**Priorité :** 🟠 Haute  
**Branche :** `feat/refresh-token-full-implementation`

**Contexte :** Le modèle RefreshToken existe mais logout()/logout_all() pas encore implémentés.

**Fichiers à modifier :**
- `app/services/auth_service.py`
- `app/routers/auth.py`
- `app/schemas/auth.py` — LogoutRequest

---

### S2-04 — Queue Logs (Audit Trail)

**Priorité :** 🟠 Haute  
**Branche :** `feat/queue-logs-audit-trail`

**Contexte :** Chaque transition de ticket doit être loggée en DB.

**Fichiers à créer :**
- `app/models/queue_log.py`
- Migration : `004_add_queue_logs_table.py`

**Source :** `.kiro/steering/decisions.md` — DONNÉES À COLLECTER

---

### S2-05 — Module Notifications (SMS + FCM)

**Priorité :** 🟡 Moyenne  
**Branche :** `feat/notifications-module`

**Fichiers à créer :**
- `app/services/notification_service.py`
- `app/models/notification.py` (optionnel)

**Triggers :**
- `TICKET_CALLED` → SMS au client
- `TICKET_DONE` → notification in-app
- `waiting_time > 30min` → alerte Rules Engine

---

### S2-06 — Analytics Pipeline base

**Priorité :** 🟡 Moyenne  
**Branche :** `feat/analytics-pipeline-base`  
**Dépend de :** S2-04

**Fichiers à créer :**
- `app/services/analytics_service.py`
- `app/routers/analytics.py`

**Données collectées :**
- Temps d'attente moyen par agence/service/heure
- Taux d'absence (ABSENT / CALLED)
- Tickets traités par agent

---

### S2-07 — Services CRUD (CRITIQUE MVP)

**Priorité :** 🔴 Critique  
**Branche :** `feat/services-crud`

**Contexte :** Le client mobile a besoin de lister les services disponibles pour prendre un ticket.

**Fichiers à créer :**
- `app/routers/services.py`
- `app/services/service_service.py`
- `app/schemas/service.py`

**Endpoints :**
```
POST /api/v1/organizations/{org_id}/agencies/{agency_id}/services
GET  /api/v1/agencies/{agency_id}/services  (public — mobile)
```

---

### S2-08 — Join by Code

**Priorité :** 🟠 Haute  
**Branche :** `feat/join-by-code`  
**Dépend de :** S2-02

**Contexte :** Permettre à un client de rejoindre une organisation via un code d'invitation.

**Source :** `.kiro/skills/01_user_membership_model.md`

**Endpoints :**
```
POST /api/v1/users/me/organizations/join
GET  /api/v1/users/me/organizations
```

---

### S2-09 — Transfert Ticket

**Priorité :** 🟡 Moyenne  
**Branche :** `feat/transfer-ticket`

**Contexte :** La machine à états prévoit `TRANSFERRED` mais pas d'endpoint.

**Endpoint :**
```
POST /api/v1/tickets/{ticket_id}/transfer
```

---

### S2-10 — Configuration File d'Attente

**Priorité :** 🟡 Moyenne  
**Branche :** `feat/agency-config`

**Contexte :** Permettre aux admins de configurer les paramètres de la file.

**Fichiers à créer :**
- `app/schemas/agency_config.py`
- `app/services/agency_config_service.py`

**Endpoints :**
```
GET  /api/v1/agencies/{agency_id}/config
PATCH /api/v1/agencies/{agency_id}/config
```

**Champs configurables :**
- `max_daily_tickets`
- `avg_service_minutes`
- `operating_hours`
- `max_wait_minutes_alert`
- `enable_sms_reminders`

---

## Règles Git Sprint 2

```bash
# Ordre de merge (important !)
S2-01 (Vital) → EN PREMIER
S2-02 (Vital) → parallèle avec S2-03 et S2-04
S2-07 (Gédéon) → peut commencer maintenant
S2-08 (Tshibangu) → après S2-02
S2-09 (Tshibangu) → peut commencer maintenant
S2-05 (Tshibangu) → peut commencer maintenant
S2-06 (Tshibangu) → après S2-04
```

---

# TONDE — Sprint 3 Backend

> Sprint 3 : Offline Sync, Intégration, Validation

## Objectif du Sprint 3

Finaliser le MVP avec :
- Synchronisation offline
- Export de données
- Tests d'intégration complets

---

## Tâches Sprint 3

### S3-01 — Export Données (CSV/Excel)

**Priorité :** 🟡 Moyenne  
**Branche :** `feat/export-data`

**Endpoints :**
```
GET /api/v1/organizations/{org_id}/tickets/export
GET /api/v1/agencies/{agency_id}/stats/export
```

**Formats :** CSV, XLSX

---

### S3-02 — Offline Sync

**Priorité :** 🔴 Critique  
**Branche :** `feat/offline-sync`  
**Dépend de :** S2-04

**Contexte :** Le marché africain subit des coupures réseau fréquentes.

**Endpoints :**
```
GET  /api/v1/sync/state
POST /api/v1/sync/actions
GET  /api/v1/sync/changes
```

**Features :**
- Idempotence par client_action_id
- Conflict detection et resolution
- Optimistic UI sync

---

### S3-03 — Health Check Détaillé

**Priorité :** 🟢 Basse  
**Branche :** `feat/health-check`

**Contexte :** Les ops ont besoin de monitoring détaillé pour Kubernetes/Prometheus.

**Endpoints :**
```
GET  /health          # Basique
GET  /health/ready    # Readiness probe
GET  /health/live     # Liveness probe
GET  /health/detailed # Métriques (admin)
```

**Métriques :**
- DB latency
- Redis latency
- Active connections
- Version, uptime

---

# TONDE — V1.5 Backend

> V1.5 : Mobile Money, Paiements, Réservations, QR Code

## Objectif V1.5

Préparer la monétisation avec :
- Paiements Mobile Money (M-Pesa, Airtel Money)
- QR Code validation
- Réservations advance

---

## Tâches V1.5

### V1.5-01 — QR Code Validation

**Priorité :** 🟠 Haute  
**Branche :** `feat/qr-code-validation`

**Contexte :** Permettre la validation de tickets via QR code scanné.

**Endpoints :**
```
GET /api/v1/tickets/qr/{qr_token}
```

**Cas d'usage :**
- Agent scanne QR pour appeler ticket
- Client scanne son ticket pour voir position
- Client scanne QR agence pour voir services

---

### V1.5-02 — Mobile Money Integration

**Priorité :** 🟠 Haute  
**Branche :** `feat/mobile-money`

**Contexte :** Permettre les paiements Mobile Money (M-Pesa, Airtel Money).

**Modèles à créer :**
- `Payment`
- `PaymentProvider`

**Endpoints :**
```
POST /api/v1/payments/mobile-money/initiate
POST /api/v1/payments/mobile-money/callback
GET  /api/v1/payments/{payment_id}
```

**Providers supportés :**
- M-Pesa (Safaricom)
- Airtel Money

---

### V1.5-03 — Réservations Advance

**Priorité :** 🟡 Moyenne  
**Branche :** `feat/reservations`

**Contexte :** Permettre de réserver un créneau à l'avance.

**Modèle à créer :**
- `Reservation`

**Endpoints :**
```
POST /api/v1/reservations
GET  /api/v1/reservations
DELETE /api/v1/reservations/{id}
```

---

### V1.5-04 — Paiement en Ligne (Stripe)

**Priorité :** 🟡 Moyenne  
**Branche :** `feat/stripe-payments`

**Contexte :** Paiement par carte bancaire via Stripe.

**Endpoints :**
```
POST /api/v1/payments/stripe/create-intent
POST /api/v1/payments/stripe/webhook
```

---

## Règles Git V1.5

```bash
# V1.5 commence après Sprint 3 complet
# V1.5-01 peut commencer pendant Sprint 3 (indépendant)
# V1.5-02 à V1.5-04 en parallèle après Sprint 3
```
