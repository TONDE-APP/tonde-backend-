# S3-02 — Design Technique

## Architecture

```
app/
├── schemas/
│   └── sync.py              # SyncRequest, SyncResponse, ConflictResponse
├── services/
│   └── sync_service.py     # Logique de sync
└── routers/
    └── sync.py             # Endpoints sync
```

## Modèle Client Action (table sync)

```python
# Table : client_actions (pour audit et idempotence)
class ClientAction(Base):
    __tablename__ = "client_actions"
    
    id: Mapped[str]  # UUID généré par le client
    user_id: Mapped[str]
    action_type: Mapped[str]  # "CREATE_TICKET", "CANCEL_TICKET"
    payload: Mapped[dict]  # JSON du payload
    created_at: Mapped[datetime]
    synced_at: Mapped[datetime | None]  # NULL = en attente
    conflict: Mapped[bool] = False
    conflict_resolution: Mapped[str | None]  # "NEW_NUMBER", "IGNORED"
```

## Schéma des endpoints

### GET /api/v1/sync/state

**Auth :** Bearer token
**Response :**
```json
{
    "tickets": [
        {
            "id": "uuid",
            "number": "A-42",
            "status": "waiting",
            "position": 5,
            "eta_minutes": 20
        }
    ],
    "last_sync": "2026-01-01T10:00:00Z",
    "current_time": "2026-01-01T10:30:00Z"
}
```

### POST /api/v1/sync/actions

**Auth :** Bearer token
**Body :**
```json
{
    "client_id": "uuid-client",
    "actions": [
        {
            "client_action_id": "uuid-action",
            "type": "CREATE_TICKET",
            "payload": {
                "agency_id": "uuid",
                "service_id": "uuid",
                "priority": "standard"
            },
            "timestamp": "2026-01-01T09:00:00Z"
        }
    ]
}
```

**Response :**
```json
{
    "results": [
        {
            "client_action_id": "uuid-action",
            "status": "SYNCED",
            "server_id": "uuid-server",
            "number": "A-42"
        },
        {
            "client_action_id": "uuid-action-2",
            "status": "CONFLICT",
            "conflict_type": "NUMBER_CONFLICT",
            "resolution": "NEW_NUMBER_GENERATED",
            "server_id": "uuid-server",
            "number": "A-43"
        }
    ],
    "last_sync": "2026-01-01T10:30:00Z"
}
```

### GET /api/v1/sync/changes

**Auth :** Bearer token
**Query params :** `?since=2026-01-01T10:00:00Z`

**Response :**
```json
{
    "tickets": [...],
    "agencies": [...],
    "services": [...],
    "changes": [
        {
            "type": "TICKET_CALLED",
            "data": {...},
            "timestamp": "2026-01-01T10:15:00Z"
        }
    ],
    "last_sync": "2026-01-01T10:30:00Z"
}
```

## Stratégies de résolution de conflits

### 1. Ticket créés simultanément
- Backend : génère un nouveau numéro
- Retourne `CONFLICT` avec `NEW_NUMBER_GENERATED`

### 2. Ticket annulé offline
- Si déjà `DONE` : ignore l'action, retourne `CONFLICT_IGNORED`

### 3. Actions en double (idempotence)
- Vérifier `client_action_id` dans la DB
- Si existe : retourner le résultat original sans re-exécuter

## Points à traiter

1. **Table client_actions** : pour idempotence et audit
2. **Conflict detection** : basée sur timestamps et état actuel
3. **Queue Logs (S2-04)** : utiliser pour l'historique des changements
4. **FCM notifications** : prévenir le client des changements pendant son absence
