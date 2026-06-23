# S3-02 — Tasks

## Tâches d'implémentation

### 1. Créer le Modèle
**Fichier :** `app/models/client_action.py`

```python
class ClientAction(Base):
    __tablename__ = "client_actions"
    
    id: Mapped[str]  # UUID du client
    user_id: Mapped[str]
    action_type: Mapped[str]  # "CREATE_TICKET", "CANCEL_TICKET"
    payload: Mapped[dict]  # JSON
    client_timestamp: Mapped[datetime]
    synced_at: Mapped[datetime | None]
    conflict: Mapped[bool] = False
    conflict_resolution: Mapped[str | None]
```

**Migration :**
```bash
alembic revision --autogenerate -m "add_client_actions_table"
```

### 2. Créer le Schema
**Fichier :** `app/schemas/sync.py`

```python
class SyncActionRequest(BaseModel):
    client_action_id: str
    type: str  # "CREATE_TICKET", "CANCEL_TICKET"
    payload: dict
    timestamp: datetime

class SyncRequest(BaseModel):
    client_id: str
    actions: list[SyncActionRequest]

class SyncResult(BaseModel):
    client_action_id: str
    status: str  # "SYNCED", "CONFLICT", "ERROR"
    conflict_type: str | None
    resolution: str | None
    server_id: str | None

class SyncResponse(BaseModel):
    results: list[SyncResult]
    last_sync: datetime

class StateResponse(BaseModel):
    tickets: list[TicketResponse]
    last_sync: datetime
    current_time: datetime
```

### 3. Créer le Service
**Fichier :** `app/services/sync_service.py`

```python
class SyncService:
    async def get_state(self, user_id: str) -> StateResponse:
        """Retourne l'état actuel pour le client."""
        
    async def process_actions(self, user_id: str, actions: list[SyncActionRequest]) -> SyncResponse:
        """Traite les actions hors-ligne."""
        
    async def get_changes(self, user_id: str, since: datetime) -> ChangesResponse:
        """Retourne les changements depuis last_sync."""
    
    async def _detect_conflict(self, action: SyncActionRequest) -> Conflict | None:
        """Détecte un conflit."""
        
    async def _resolve_conflict(self, action: SyncActionRequest, conflict: Conflict) -> SyncResult:
        """Résout un conflit."""
```

### 4. Créer le Router
**Fichier :** `app/routers/sync.py`

```python
@router.get("/sync/state", summary="État actuel pour sync")
async def get_sync_state(current_user: User = Depends(get_current_user)):
    service = SyncService(db)
    return await service.get_state(current_user.id)

@router.post("/sync/actions", summary="Envoyer les actions hors-ligne")
async def sync_actions(
    body: SyncRequest,
    current_user: User = Depends(get_current_user)
):
    service = SyncService(db)
    return await service.process_actions(current_user.id, body.actions)

@router.get("/sync/changes", summary="Récupérer les changements")
async def get_changes(
    since: datetime = Query(...),
    current_user: User = Depends(get_current_user)
):
    service = SyncService(db)
    return await service.get_changes(current_user.id, since)
```

## Tests à écrire

```python
test_sync_state_returns_current_tickets
test_sync_action_create_ticket_success
test_sync_action_idempotent_on_duplicate
test_sync_conflict_detected_on_double_ticket
test_sync_conflict_resolved_with_new_number
test_sync_changes_since_timestamp
test_sync_ignore_cancelled_ticket_action
```

## Checklist PR

- [ ] Table client_actions créée
- [ ] Migration Alembic créée
- [ ] Schemas sync créés
- [ ] SyncService créé
- [ ] Endpoint GET /sync/state
- [ ] Endpoint POST /sync/actions
- [ ] Endpoint GET /sync/changes
- [ ] Idempotence par client_action_id
- [ ] Conflict detection
- [ ] Conflict resolution (last-write-wins)
- [ ] Tests passent
