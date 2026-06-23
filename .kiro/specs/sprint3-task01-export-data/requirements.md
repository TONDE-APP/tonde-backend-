# S3-01 — Export Données (CSV/Excel)

## Contexte

Les administrateurs et superviseurs ont besoin d'exporter les données pour :
- Rapports financiers
- Audits
- Analyses externes (Excel, Google Sheets)
- Archivage

## Objectif

Créer des endpoints pour exporter les données en CSV et Excel.

## Scope

### Endpoints à créer

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/v1/organizations/{org_id}/tickets/export` | Exporter les tickets (CSV) |
| GET | `/api/v1/agencies/{agency_id}/tickets/export` | Exporter les tickets d'une agence |
| GET | `/api/v1/agencies/{agency_id}/stats/export` | Exporter les stats (CSV) |

### Formats supportés

| Format | Extension | Usage |
|--------|----------|-------|
| CSV | `.csv` | Rapports, Google Sheets |
| Excel | `.xlsx` | Analyses, graphiques |

### Paramètres

```python
?format=csv|xlsx
?from=2026-01-01        # Date début
?to=2026-01-31          # Date fin
?status=waiting|called  # Filtrer par statut
?service_id=uuid         # Filtrer par service
```

## Permissions

| Rôle | Permissions |
|------|-------------|
| SUPERVISOR | Export de son agence |
| ADMIN_AGENCY | Export de son agence |
| ADMIN_ORG | Export de toute l'organisation |
| SUPER_ADMIN | Export global |

## Contraintes

1. Respecter les limites d'export (max 100 000 lignes)
2. Timeout approprié pour les gros exports
3. Logs des exports pour audit trail
