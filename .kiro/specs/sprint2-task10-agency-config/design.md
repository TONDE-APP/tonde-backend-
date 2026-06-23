# S2-10 — Design Technique

## Architecture

```
app/
├── schemas/
│   └── agency_config.py      # AgencyConfigRequest, AgencyConfigResponse
├── services/
│   └── agency_config_service.py
└── routers/
    └── agencies.py            # Ajouter les endpoints
```

## Modèle Optionnel

```python
# Option 1: Ajouter champs dans Agency
class Agency(Base):
    # ... champs existants ...
    max_daily_tickets: Mapped[int] = 200
    avg_service_minutes: Mapped[int] = 5
    max_wait_minutes_alert: Mapped[int] = 30
    operating_hours: Mapped[dict]  # JSON
    enable_sms_reminders: Mapped[bool] = True

# Option 2: Table séparée (si config complexe)
class AgencyConfig(Base):
    agency_id: str
    config_key: str  # "max_daily_tickets"
    config_value: Any
```

**Recommandation :** Option 1 (champs dans Agency) pour les configs simples.

## Endpoints

### GET /api/v1/agencies/{agency_id}/config

```json
{
    "max_daily_tickets": 200,
    "avg_service_minutes": 5,
    "max_wait_minutes_alert": 30,
    "operating_hours": {
        "monday": {"open": "08:00", "close": "17:00"},
        "tuesday": {"open": "08:00", "close": "17:00"}
    },
    "enable_sms_reminders": true,
    "reminder_interval_minutes": 10,
    "languages": ["fr", "en"]
}
```

### PATCH /api/v1/agencies/{agency_id}/config

```json
{
    "avg_service_minutes": 10,
    "max_wait_minutes_alert": 45
}
```

## Points à traiter

1. **Validation** : heures valides, nombres positifs
2. **Valeurs par défaut** : si non configuré, retourner defaults
3. **Audit** : logger les changements dans queue_log (S2-04)
4. **Intégration** : utiliser avg_service_minutes dans TicketService pour ETA
