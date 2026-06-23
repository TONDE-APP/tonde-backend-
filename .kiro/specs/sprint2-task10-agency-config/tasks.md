# S2-10 — Tasks

## Tâches d'implémentation

### 1. Ajouter champs à Agency
**Fichier :** `app/models/agency.py` (ou branch.py après S2-01)

```python
max_daily_tickets: Mapped[int] = 200
avg_service_minutes: Mapped[int] = 5
max_wait_minutes_alert: Mapped[int] = 30
operating_hours: Mapped[dict] = {}  # JSON
enable_sms_reminders: Mapped[bool] = True
reminder_interval_minutes: Mapped[int] = 10
supported_languages: Mapped[list[str]] = ["fr"]
```

**Migration :**
```bash
alembic revision --autogenerate -m "add_agency_config_fields"
```

### 2. Ajouter les Schemas
**Fichier :** `app/schemas/agency_config.py`

```python
class OperatingHours(BaseModel):
    open: str  # "08:00"
    close: str  # "17:00"

class AgencyConfigRequest(BaseModel):
    max_daily_tickets: int | None = None
    avg_service_minutes: int | None = None
    max_wait_minutes_alert: int | None = None
    operating_hours: dict | None = None
    enable_sms_reminders: bool | None = None
    reminder_interval_minutes: int | None = None
    supported_languages: list[str] | None = None

class AgencyConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    max_daily_tickets: int
    avg_service_minutes: int
    max_wait_minutes_alert: int
    operating_hours: dict
    enable_sms_reminders: bool
    reminder_interval_minutes: int
    supported_languages: list[str]
```

### 3. Ajouter au Service
**Fichier :** `app/services/agency_service.py`

```python
async def get_agency_config(self, agency_id: str, org_id: str) -> AgencyConfigResponse:
    """Retourne la configuration de l'agence."""

async def update_agency_config(
    self, agency_id: str, org_id: str, config: AgencyConfigRequest
) -> AgencyConfigResponse:
    """Met à jour la configuration."""
```

### 4. Ajouter au Router
**Fichier :** `app/routers/agencies.py`

```python
@router.get("/{agency_id}/config", summary="Configuration de l'agence")
async def get_config(
    agency_id: str,
    current_user: User = Depends(get_current_agent)
):
    return await service.get_agency_config(agency_id, current_user.org_id)

@router.patch("/{agency_id}/config", summary="Modifier la configuration")
async def update_config(
    agency_id: str,
    config: AgencyConfigRequest,
    current_user: User = Depends(get_current_admin)
):
    return await service.update_agency_config(agency_id, current_user.org_id, config)
```

## Tests à écrire

```python
test_get_config_returns_defaults
test_update_config_as_admin
test_update_config_validates_positive_numbers
test_config_used_in_eta_calculation
test_operating_hours_validation
```

## Checklist PR

- [ ] Champs ajoutés au modèle Agency
- [ ] Migration créée
- [ ] Schemas créés
- [ ] GET /config endpoint
- [ ] PATCH /config endpoint
- [ ] Validation des valeurs
- [ ] Intégration avec TicketService pour ETA
- [ ] Tests passent
