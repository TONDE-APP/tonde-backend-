# S3-03 — Health Check Détaillé

## Contexte

Actuellement, le health check est basique : retourne OK si le serveur répond. Les ops ont besoin de vérifier :
- Connexion à la DB
- Connexion à Redis
- Latence des services externes
- Nombre de connexions actives

## Objectif

Créer un health check détaillé pour les opérations et le monitoring (Prometheus, Datadog, etc.).

## Scope

### Endpoint à créer

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/health` | Health check basique |
| GET | `/health/detailed` | Health check détaillé (admin) |
| GET | `/health/ready` | Readiness probe (Kubernetes) |
| GET | `/health/live` | Liveness probe (Kubernetes) |

### Métriques à retourner

```json
{
    "status": "healthy",
    "timestamp": "2026-01-01T10:00:00Z",
    "version": "1.0.0",
    "uptime_seconds": 86400,
    "checks": {
        "database": {
            "status": "healthy",
            "latency_ms": 5
        },
        "redis": {
            "status": "healthy",
            "latency_ms": 2
        },
        "africas_talking": {
            "status": "unknown",
            "latency_ms": null
        }
    },
    "metrics": {
        "active_connections": 45,
        "requests_per_minute": 120,
        "queue_size": 234
    }
}
```

## Contraintes

1. `/health` doit être rapide (< 100ms) et sans auth
2. `/health/detailed` peut être plus lent mais protégé
3. Formats compatibles Prometheus (optionnel)
