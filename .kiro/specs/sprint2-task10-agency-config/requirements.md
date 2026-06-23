# S2-10 — Configuration File d'Attente

## Contexte

Actuellement, les paramètres de la file d'attente sont stockés directement dans le modèle `Agency` ou hardcodés :
- `max_daily_tickets` : nombre max de tickets par jour
- `avg_service_minutes` : temps moyen de service
- `max_wait_minutes_alert` : seuil d'alerte pour temps d'attente
- `operating_hours` : heures d'ouverture

Ces valeurs doivent être configurables par agence sans modifier le code.

## Objectif

Créer un système de configuration flexible pour les agences.

## Scope

### Endpoints à créer

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/v1/agencies/{agency_id}/config` | Lire la configuration |
| PATCH | `/api/v1/agencies/{agency_id}/config` | Modifier la configuration |
| GET | `/api/v1/agencies/{agency_id}/config/valid-hours` | Heures d'ouverture |

### Champs configurables

```python
{
    "max_daily_tickets": 200,      # Max tickets/jour (0 = illimité)
    "avg_service_minutes": 5,      # Temps moyen de service
    "max_wait_minutes_alert": 30, # Alerte si attente > 30min
    "operating_hours": {           # Heures d'ouverture
        "monday": {"open": "08:00", "close": "17:00"},
        "tuesday": {"open": "08:00", "close": "17:00"},
        # ...
    },
    "enable_sms_reminders": true,
    "reminder_interval_minutes": 10,
    "languages": ["fr", "en", "sw"],  # Langues supportées
}
```

## Permissions

| Rôle | Permissions |
|------|-------------|
| ADMIN_ORG | Config de toutes les agences de son org |
| ADMIN_AGENCY | Config de son agence uniquement |

## Contraintes

1. Validation des valeurs (ex: max_daily_tickets > 0)
2. Audit des modifications (qui a changé quoi)
3. Pas de suppression de config — toujours une valeur par défaut
