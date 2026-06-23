# S3-01 — Design Technique

## Architecture

```
app/
├── services/
│   └── export_service.py    # Logique d'export CSV/Excel
└── routers/
    └── exports.py           # Endpoints d'export
```

## Dépendances

```python
# requirements.txt
openpyxl>=3.1.0  # Pour Excel
```

## Implémentation CSV

```python
import csv
from fastapi.responses import StreamingResponse

async def export_tickets_csv(org_id: str, params: ExportParams) -> StreamingResponse:
    """Génère un CSV stream pour les tickets."""
    tickets = await query_tickets(org_id, params)
    
    async def generate():
        # Header
        yield "ID,Ticket,Status,Priority,Created At,Called At,Served At,Wait Time,Service,Agency\n"
        
        for ticket in tickets:
            yield f"{ticket.id},{ticket.number},{ticket.status},{ticket.priority},{ticket.created_at},{ticket.called_at},{ticket.served_at},{ticket.actual_wait_minutes},{ticket.service_id},{ticket.agency_id}\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tickets.csv"}
    )
```

## Implémentation Excel

```python
from openpyxl import Workbook
from fastapi.responses import StreamingResponse

async def export_tickets_xlsx(org_id: str, params: ExportParams) -> StreamingResponse:
    """Génère un fichier Excel pour les tickets."""
    tickets = await query_tickets(org_id, params)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Tickets"
    
    # Headers
    headers = ["ID", "Numéro", "Statut", "Priorité", "Créé le", "Called le", "Servi le", "Temps attente"]
    ws.append(headers)
    
    # Data
    for ticket in tickets:
        ws.append([
            ticket.id,
            ticket.number,
            ticket.status.value,
            ticket.priority.value,
            ticket.created_at.isoformat(),
            ticket.called_at.isoformat() if ticket.called_at else "",
            ticket.served_at.isoformat() if ticket.served_at else "",
            ticket.actual_wait_minutes,
        ])
    
    # Return as bytes
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=tickets.xlsx"}
    )
```

## Points à traiter

1. **Stream pour gros fichiers** : ne pas charger tout en mémoire
2. **Dépend de S2-04 (queue_logs)** : utiliser les logs pour enrichir les données
3. **Validation des params** : dates, limites
4. **Audit** : logger qui exporte quoi
