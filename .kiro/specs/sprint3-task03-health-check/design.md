# S3-03 — Design Technique

## Architecture

```
app/
├── core/
│   └── health.py             # HealthCheckService
└── main.py                    # Ajouter les routes
```

## Implémentation

```python
# app/core/health.py
from datetime import datetime, timezone
import asyncio
from sqlalchemy import text
from app.core.redis import get_redis

class HealthCheckService:
    def __init__(self, db):
        self.db = db
    
    async def basic_check(self) -> dict:
        """Health check rapide — OK si le serveur répond."""
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    async def detailed_check(self) -> dict:
        """Health check complet avec métriques."""
        start = datetime.now(timezone.utc)
        
        # Vérifier DB
        db_status = await self._check_database()
        
        # Vérifier Redis
        redis_status = await self._check_redis()
        
        # Calculer uptime (depuis le démarrage de l'app)
        # Stocké dans app.state.start_time
        
        overall = "healthy"
        if db_status["status"] == "unhealthy" or redis_status["status"] == "unhealthy":
            overall = "unhealthy"
        elif db_status["status"] == "degraded" or redis_status["status"] == "degraded":
            overall = "degraded"
        
        return {
            "status": overall,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": settings.VERSION,
            "uptime_seconds": self._get_uptime(),
            "checks": {
                "database": db_status,
                "redis": redis_status,
            },
            "metrics": await self._get_metrics()
        }
    
    async def _check_database(self) -> dict:
        """Vérifie la connexion DB."""
        try:
            import time
            start = time.time()
            await self.db.execute(text("SELECT 1"))
            latency = int((time.time() - start) * 1000)
            
            return {"status": "healthy", "latency_ms": latency}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_redis(self) -> dict:
        """Vérifie la connexion Redis."""
        try:
            import time
            r = await get_redis()
            start = time.time()
            await r.ping()
            latency = int((time.time() - start) * 1000)
            
            return {"status": "healthy", "latency_ms": latency}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _get_metrics(self) -> dict:
        """Retourne les métriques."""
        try:
            r = await get_redis()
            info = await r.info("clients")
            return {
                "active_connections": info.get("connected_clients", 0),
                "redis_connected": True
            }
        except:
            return {"active_connections": 0, "redis_connected": False}
```

## Routes dans main.py

```python
# Basic health — pas d'auth
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Readiness probe (Kubernetes)
@app.get("/health/ready")
async def readiness():
    # Vérifie que la DB et Redis sont connectées
    pass

# Liveness probe (Kubernetes)  
@app.get("/health/live")
async def liveness():
    return {"status": "alive"}

# Detailed health — protégé
@app.get("/health/detailed")
async def detailed_health(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(get_current_super_admin)  # Super admin only
):
    service = HealthCheckService(db)
    return await service.detailed_check()
```

## Points à traiter

1. **Kubernetes probes** : `/health/ready` et `/health/live` sont标准的 K8s probes
2. **Prometheus metrics** : optionnel, utiliser `prometheus_client`
3. **Cache** : ne pas faire les checks à chaque appel (cache 5s)
