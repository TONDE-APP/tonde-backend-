# S2-07 — Design Technique

## Architecture

```
app/
├── schemas/
│   └── service.py          # CreateServiceRequest, ServiceResponse, UpdateServiceRequest
├── services/
│   └── service_service.py  # Logique métier CRUD
└── routers/
    └── services.py         # Endpoints HTTP
```

## Modèle existant (app/models/agency.py)

```python
class Service(Base):
    __tablename__ = "services"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True)
    agency_id: Mapped[str] = mapped_column(String(36), ForeignKey("agencies.id"))
    
    name: Mapped[str]
    description: Mapped[str | None]
    ticket_prefix: Mapped[str]  # A, B, C...
    avg_duration_minutes: Mapped[int] = 5
    is_active: Mapped[bool] = True
```

## Schéma des endpoints

### POST /api/v1/organizations/{org_id}/agencies/{agency_id}/services

**Auth :** ADMIN_ORG ou ADMIN_AGENCY
**Body :**
```json
{
    "name": "Caisse",
    "description": "Guichets de dépôt et retrait",
    "ticket_prefix": "A",
    "avg_duration_minutes": 5
}
```
**Response 201 :**
```json
{
    "id": "uuid",
    "name": "Caisse",
    "ticket_prefix": "A",
    "is_active": true
}
```

### GET /api/v1/agencies/{agency_id}/services (PUBLIC)

**Auth :** Aucune (public)
**Response 200 :**
```json
[
    {
        "id": "uuid",
        "name": "Caisse",
        "ticket_prefix": "A",
        "avg_duration_minutes": 5
    },
    {
        "id": "uuid-2",
        "name": "Crédit",
        "ticket_prefix": "B",
        "avg_duration_minutes": 15
    }
]
```

## Points à traiter

1. **Ticket prefix unique par agence** : contrainte DB ou validation service
2. **Service avec tickets actifs** : count tickets avant suppression, sinon erreur 409
3. **Organisation de la migration Agency → Branch** : ce module dépend de S2-01
