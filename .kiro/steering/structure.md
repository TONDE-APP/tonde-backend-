# TONDE — Structure du projet

## Arborescence

```
tonde-backend/
├── app/
│   ├── main.py                  # Point d'entrée FastAPI, lifespan, CORS, routers
│   ├── core/
│   │   ├── config.py            # Settings Pydantic depuis .env (instance `settings`)
│   │   ├── database.py          # Engine SQLAlchemy async, Base, get_db(), create_tables()
│   │   ├── deps.py              # Dépendances FastAPI : get_current_user, get_current_agent
│   │   ├── redis.py             # Client Redis async (connexion, helpers file)
│   │   └── security.py         # JWT, bcrypt, OTP (DEV_OTP = "123456")
│   ├── models/                  # Modèles SQLAlchemy (tables PostgreSQL)
│   │   ├── user.py              # User, UserRole enum
│   │   ├── ticket.py            # Ticket, TicketStatus, TicketPriority enums
│   │   └── agency.py           # Agency, Service
│   ├── schemas/                 # Schémas Pydantic v2 (validation I/O)
│   │   ├── auth.py              # RegisterPhoneRequest, VerifyOtpRequest, AuthResponse...
│   │   └── ticket.py           # CreateTicketRequest, TicketResponse...
│   ├── routers/                 # Endpoints FastAPI (HTTP handlers)
│   │   ├── auth.py              # /api/v1/auth/...
│   │   └── tickets.py          # /api/v1/tickets/...
│   ├── services/                # Logique métier (couche service)
│   │   ├── auth_service.py      # AuthService : register, verify_otp, login, refresh
│   │   └── ticket_service.py   # TicketService : create, get, cancel, call_next, history
│   └── websocket/
│       └── queue_ws.py         # QueueWebSocketManager (instance globale `ws_manager`)
├── tests/                       # Tests pytest + pytest-asyncio
├── .env                         # Variables d'environnement (ne jamais committer)
├── docker-compose.yml           # API + PostgreSQL 15 + Redis 7 + Redis Commander
├── Dockerfile                   # Image de l'API
└── requirements.txt             # Dépendances épinglées
```

## Conventions d'architecture

### Pattern en couches (obligatoire)

```
Router → Service → Model / Redis
```

- **Router** (`routers/`) : reçoit la requête HTTP, appelle le service, retourne la réponse. Pas de logique métier ici.
- **Service** (`services/`) : toute la logique métier, accès DB et Redis. Instancié avec `db: AsyncSession`.
- **Model** (`models/`) : définition SQLAlchemy. Pas de logique, seulement la structure.
- **Schema** (`schemas/`) : validation Pydantic v2 des entrées/sorties. Séparé des modèles DB.

### Dépendances injectées

| Dépendance | Source | Usage |
|-----------|--------|-------|
| `db: AsyncSession` | `Depends(get_db)` | Toute route qui touche la DB |
| `current_user: User` | `Depends(get_current_user)` | Routes authentifiées |
| `current_user: User` | `Depends(get_current_agent)` | Routes agent/manager/admin |

### Préfixes de routes

```
/api/v1/auth/...      → routers/auth.py
/api/v1/tickets/...   → routers/tickets.py
/                     → health check, root info
/health               → monitoring Docker/infra
```

### Modèles SQLAlchemy

- Utiliser `Mapped[type]` et `mapped_column()` (SQLAlchemy 2.0)
- Clés primaires : UUID v4 en `String(36)`
- Enums Python définis dans le même fichier que le modèle
- `created_at` / `updated_at` sur toutes les entités
- Toute entité métier doit prévoir `org_id` / `tenant_id` (multi-tenant)

### Schémas Pydantic

- Séparés des modèles DB
- Validators avec `@field_validator` et `@classmethod`
- Réponses d'erreur standardisées : `{"success": false, "error": {"code": "...", "message": "..."}}`
- `Config.from_attributes = True` pour les schémas qui lisent depuis un ORM

### Gestion des erreurs

- `HTTPException` avec `detail` structuré : `{"code": "CODE_ERREUR", "message": "..."}`
- Handlers globaux 404 et 500 dans `main.py`
- `rollback()` automatique en cas d'exception dans `get_db()`

### WebSocket

- Instance globale `ws_manager` dans `app/websocket/queue_ws.py`
- Connexions indexées par `ticket_id` et par `agency_id`
- Événements principaux : `your_turn`, `queue_update`, `ticket_called`, `broadcast_message`
- Le Queue Engine publie les événements, le WebSocket les diffuse (découplage obligatoire)

### Redis

- Helpers centralisés dans `app/core/redis.py`
- Utilisé pour : file d'attente (sorted set par priorité), OTP, cache, Pub/Sub
- Clés nommées avec le pattern `tonde:{agency_id}:queue`

## Modules à créer (MVP restant)

Les modules suivants sont référencés dans les modèles mais pas encore créés :

- `organizations/` — gestion multi-tenant
- `branches/` — succursales d'une organisation  
- `counters/` — guichets
- `employees/` — agents et managers
- `notifications/` — SMS, FCM, in-app
- `analytics/` — stats et reporting

Suivre le même pattern : `model → schema → service → router`.

---

## Mises à jour Sprint 1 — Structure réelle du projet

### Modules déjà implémentés (état actuel)

```
app/
├── models/
│   ├── organization.py   ✅ Créé
│   ├── agency.py         ✅ Créé (sera renommé branch.py en Sprint 2)
│   ├── counter.py        ✅ Créé
│   ├── employee.py       ✅ Créé
│   ├── user.py           ✅ Créé
│   ├── ticket.py         ✅ Créé
│   └── refresh_token.py  🔜 À créer — TASK-02
├── schemas/
│   ├── auth.py           ✅ Créé
│   ├── agency.py         ✅ Créé
│   ├── counter.py        ✅ Créé
│   ├── employee.py       ✅ Créé
│   ├── organization.py   ✅ Créé
│   └── ticket.py         ✅ Créé
├── services/
│   ├── auth_service.py       ✅ Créé
│   ├── agency_service.py     ✅ Créé
│   ├── counter_service.py    ✅ Créé
│   ├── employee_service.py   ✅ Créé
│   ├── organization_service.py ✅ Créé
│   └── ticket_service.py     ✅ Créé
├── routers/
│   ├── auth.py           ✅ Créé
│   ├── agencies.py       ✅ Créé
│   ├── counters.py       ✅ Créé
│   ├── employees.py      ✅ Créé
│   ├── organizations.py  ✅ Créé
│   └── tickets.py        ✅ Créé
├── websocket/
│   ├── queue_ws.py       ✅ Créé (listener non branché — TASK-05)
│   └── events.py         ✅ Créé
└── core/
    ├── config.py         ✅ Créé
    ├── database.py       ✅ Créé
    ├── deps.py           ✅ Créé
    ├── redis.py          ✅ Créé
    ├── security.py       ✅ Créé
    └── middlewares.py    🔜 À créer — TASK-06
```

### Clé Redis officielle (après TASK-04)

```
tonde:{org_id}:{agency_id}:{service_id}:queue   → file d'attente (Sorted Set)
tonde:otp:{phone}                                → OTP hashé (TTL 5 min)
tonde:otp_attempts:{phone}                       → compteur tentatives OTP
tonde:cache:{key}                                → cache général
tonde:events:{org_id}                            → canal Redis Pub/Sub
```

### Modules Sprint 2 (ne pas implémenter avant validation Sprint 1)

- `app/models/user_organization.py` — table pivot User ↔ Organization (Décision 7)
- `app/models/branch.py` — renommage de agency.py (Décision 8)
- `app/services/notification_service.py` — SMS + FCM
- `app/services/analytics_service.py` — collecte de données
- `app/models/queue_log.py` — audit trail des transitions
