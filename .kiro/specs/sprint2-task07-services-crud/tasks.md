# S2-07 — Tasks

## Tâches d'implémentation

### 1. Créer le Schema
**Fichier :** `app/schemas/service.py`

```python
class CreateServiceRequest(BaseModel):
    name: str                    # ex: "Caisse"
    description: str | None
    ticket_prefix: str = "A"     # ex: "A", "B", "C"
    avg_duration_minutes: int = 5

class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str | None
    ticket_prefix: str
    avg_duration_minutes: int
    is_active: bool

class UpdateServiceRequest(BaseModel):
    name: str | None
    description: str | None
    ticket_prefix: str | None
    avg_duration_minutes: int | None
    is_active: bool | None
```

### 2. Créer le Service
**Fichier :** `app/services/service_service.py`

```python
class ServiceService:
    async def create_service(...) -> ServiceResponse
    async def get_services_by_agency(...) -> list[ServiceResponse]
    async def get_service(...) -> ServiceResponse
    async def update_service(...) -> ServiceResponse
    async def delete_service(...) -> dict
```

### 3. Créer le Router
**Fichier :** `app/routers/services.py`

```python
# Admin endpoints
POST   /api/v1/organizations/{org_id}/agencies/{agency_id}/services
GET    /api/v1/organizations/{org_id}/agencies/{agency_id}/services
GET    /api/v1/organizations/{org_id}/agencies/{agency_id}/services/{service_id}
PATCH  /api/v1/organizations/{org_id}/agencies/{agency_id}/services/{service_id}
DELETE /api/v1/organizations/{org_id}/agencies/{agency_id}/services/{service_id}

# Public endpoint (mobile)
GET    /api/v1/agencies/{agency_id}/services
GET    /api/v1/agencies/{agency_id}/services/{service_id}
```

### 4. Enregistrer dans main.py
```python
from app.routers import services
app.include_router(services.router, prefix="/api/v1", tags=["Services"])
```

## Tests à écrire

```python
test_create_service_as_admin_org
test_create_service_as_admin_agency
test_create_service_duplicate_prefix_fails
test_list_services_public_vs_admin
test_update_service_as_admin
test_delete_service_with_active_tickets_fails
test_delete_service_success
```

## Checklist PR

- [ ] Schema créé dans `app/schemas/service.py`
- [ ] Service créé dans `app/services/service_service.py`
- [ ] Router créé dans `app/routers/services.py`
- [ ] Endpoints admin protégés RBAC
- [ ] Endpoint public accessible sans auth (lecture seule)
- [ ] Validateur ticket_prefix unique par agence
- [ ] Protection suppression avec tickets actifs
- [ ] Tests passent
