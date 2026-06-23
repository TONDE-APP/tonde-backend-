# S3-01 — Tasks

## Tâches d'implémentation

### 1. Ajouter openpyxl aux dépendances
**Fichier :** `requirements.txt`
```
openpyxl>=3.1.0
```

### 2. Créer le Schema
**Fichier :** `app/schemas/export.py`

```python
from enum import Enum

class ExportFormat(str, Enum):
    CSV = "csv"
    XLSX = "xlsx"

class ExportParams(BaseModel):
    format: ExportFormat = ExportFormat.CSV
    from_date: datetime | None = None
    to_date: datetime | None = None
    status: list[TicketStatus] | None = None
    service_id: str | None = None
    limit: int = 100000
```

### 3. Créer le Service
**Fichier :** `app/services/export_service.py`

```python
class ExportService:
    async def export_tickets_csv(...) -> StreamingResponse
    async def export_tickets_xlsx(...) -> StreamingResponse
    async def export_stats_csv(...) -> StreamingResponse
```

### 4. Créer le Router
**Fichier :** `app/routers/exports.py`

```python
@router.get("/organizations/{org_id}/tickets/export")
async def export_org_tickets(
    org_id: str,
    format: ExportFormat = Query(ExportFormat.CSV),
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    ...
):
    service = ExportService(db)
    return await service.export_tickets(org_id, params)

@router.get("/agencies/{agency_id}/tickets/export")
async def export_agency_tickets(...):

@router.get("/agencies/{agency_id}/stats/export")
async def export_agency_stats(...):
```

## Tests à écrire

```python
test_export_tickets_csv
test_export_tickets_xlsx
test_export_with_date_filter
test_export_with_status_filter
test_export_limit_enforced
test_export_large_dataset_streaming
test_export_unauthorized_org_fails
```

## Checklist PR

- [ ] openpyxl ajouté aux dépendances
- [ ] Schema ExportParams créé
- [ ] ExportService créé
- [ ] Endpoints CSV et XLSX
- [ ] StreamingResponse pour gros fichiers
- [ ] Validation des params
- [ ] Audit log des exports
- [ ] Tests passent
