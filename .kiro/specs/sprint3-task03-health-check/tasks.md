# S3-03 — Tasks

## Tâches d'implémentation

### 1. Créer le Service
**Fichier :** `app/core/health.py`

```python
class HealthCheckService:
    async def basic_check(self) -> dict
    async def detailed_check(self) -> dict
    async def readiness_check(self) -> dict
    async def _check_database(self) -> dict
    async def _check_redis(self) -> dict
    async def _get_metrics(self) -> dict
```

### 2. Ajouter les Routes
**Fichier :** `app/main.py`

```python
@app.get("/health", tags=["Health"])
async def health_check():
    """Basic health check — toujours OK si le serveur répond."""
    return {"status": "healthy"}

@app.get("/health/ready", tags=["Health"])
async def readiness():
    """Kubernetes readiness probe."""
    return await health_service.readiness_check()

@app.get("/health/live", tags=["Health"])
async def liveness():
    """Kubernetes liveness probe."""
    return {"status": "alive"}

@app.get("/health/detailed", tags=["Health"])
async def detailed_health(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(get_current_super_admin)
):
    """Detailed health check avec métriques — super admin only."""
    service = HealthCheckService(db)
    return await service.detailed_check()
```

### 3. Ajouter les dépendances
**Fichier :** `requirements.txt`
```
# Pour Prometheus (optionnel)
prometheus-client>=0.19.0
```

## Tests à écrire

```python
test_basic_health_returns_200
test_readiness_returns_db_status
test_liveness_returns_alive
test_detailed_health_requires_auth
test_detailed_health_includes_latency
test_health_unhealthy_when_db_down
```

## Checklist PR

- [ ] HealthCheckService créé
- [ ] GET /health endpoint
- [ ] GET /health/ready endpoint
- [ ] GET /health/live endpoint
- [ ] GET /health/detailed endpoint (protégé)
- [ ] DB check avec latence
- [ ] Redis check avec latence
- [ ] Tests passent
