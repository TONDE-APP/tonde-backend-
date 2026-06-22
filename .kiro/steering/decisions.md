# TONDE — Décisions d'Architecture

> Source de vérité pour toutes les décisions techniques validées par Vital.
> Tout agent IA ou développeur doit lire ce fichier avant de toucher au code.
> Dernière mise à jour : Juin 2026

---

## DÉCISION 1 — Règle "1 ticket actif global" par utilisateur

**Statut :** ✅ Validé — Sprint 1  
**Décidé par :** Vital

### Règle
Un utilisateur ne peut posséder qu'**un seul ticket actif sur toute la plateforme TONDE** au même moment. La restriction s'applique globalement, sans filtre par agence.

### Statuts considérés "actifs"
```python
ACTIVE_STATUSES = [
    TicketStatus.WAITING,
    TicketStatus.CALLED,
    TicketStatus.SERVING,
    TicketStatus.ABSENT,
    TicketStatus.TRANSFERRED,
    TicketStatus.INCOMPLETE,
]
```

### Scénario interdit
Avoir un ticket `WAITING` à la BANCOBU **et** tenter de prendre un ticket au CHUK → le système bloque le deuxième avec HTTP 409.

### Condition de libération
L'utilisateur doit attendre que son ticket passe en `DONE` ou `CANCELLED` avant de pouvoir en prendre un nouveau.

### Réponse d'erreur (HTTP 409)
```json
{
  "code": "TICKET_ALREADY_ACTIVE",
  "message": "Vous avez déjà un ticket actif (A-12 — statut : waiting). Attendez qu'il soit terminé ou annulez-le.",
  "active_ticket_id": "uuid-du-ticket",
  "active_ticket_number": "A-12"
}
```
Le champ `active_ticket_id` permet au mobile de rediriger directement vers le ticket actif.

### Impact code
- `app/services/ticket_service.py` — méthode `_get_active_ticket()` : supprimer le filtre `agency_id`
- `app/services/ticket_service.py` — `create_ticket()` : passer `ACTIVE_STATUSES` étendu

---

## DÉCISION 2 — OTP hashé dans Redis (sécurité critique)

**Statut :** ✅ Validé — Sprint 1 (priorité immédiate)  
**Décidé par :** Vital

### Règle
L'OTP ne doit **jamais** être stocké en clair dans Redis. Seul le `sha256(otp)` est persisté.

### Implémentation
```python
import hashlib

def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

# Stockage
await redis.setex(f"tonde:otp:{phone}", ttl, _hash_otp(otp))

# Vérification
if hashlib.sha256(otp_saisi.encode()).hexdigest() != stored_hash:
    raise HTTPException(400, ...)
```

### Impact code
- `app/core/redis.py` — `save_otp()` : hasher avant `setex`
- `app/core/redis.py` — `get_otp()` : retourne le hash (pas le clair)
- `app/services/auth_service.py` — `verify_otp()` : comparer les hash

---

## DÉCISION 3 — Refresh Token persisté en base de données

**Statut :** ✅ Validé — Sprint 1 (priorité haute)  
**Décidé par :** Vital

### Justification
Le refresh token stateless actuel ne permet pas :
- Logout propre et sécurisé
- Révocation de session à distance
- Gestion multi-device (plusieurs sessions par compte)

### Nouvelle table `refresh_tokens`
```python
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str]              # UUID PK
    user_id: Mapped[str]         # FK → users.id
    token_hash: Mapped[str]      # sha256 du token — JAMAIS en clair
    device_id: Mapped[str|None]  # tracking multi-device
    ip_address: Mapped[str|None]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime|None]  # NULL = valide
    created_at: Mapped[datetime]
```

### Règles
- Le token JWT lui-même est signé normalement
- Le hash est stocké en DB pour permettre la révocation
- À chaque `POST /auth/refresh` → rotation : l'ancien token est révoqué, un nouveau est créé
- `POST /auth/logout` → `revoked_at = now()` pour le token concerné
- Multi-device supporté : plusieurs lignes `refresh_tokens` pour un même `user_id`

### Nouveaux endpoints
```
POST /api/v1/auth/logout        → révoque le refresh token du body
POST /api/v1/auth/logout/all    → révoque tous les tokens de l'utilisateur
```

---

## DÉCISION 4 — Clés Redis segmentées par service

**Statut :** ✅ Validé — Sprint 1  
**Décidé par :** Vital

### Ancienne clé (abandonnée)
```
tonde:{org_id}:{agency_id}:queue
```

### Nouvelle clé (obligatoire)
```
tonde:{org_id}:{agency_id}:{service_id}:queue
```

### Justification
Chaque service (Caisse, Crédit, Conseiller, VIP) doit avoir sa propre file indépendante dans la même agence.

### Impact code
- `app/core/redis.py` — fonction `_queue_key()` : ajouter `service_id`
- Toutes les fonctions Redis de file : `add_to_queue`, `get_queue_position`, `get_queue_size`, `remove_from_queue`, `get_next_ticket`, `get_queue_snapshot` — ajout du paramètre `service_id`
- `app/services/ticket_service.py` — cascade des appels Redis
- `app/schemas/ticket.py` — `CallNextRequest` : ajouter `service_id`
- `app/routers/tickets.py` — `call_next` : passer `service_id`

---

## DÉCISION 5 — Redis Pub/Sub activé pour le multi-serveurs

**Statut :** ✅ Validé — Sprint 1  
**Décidé par :** Vital

### Problème actuel
Le `start_redis_listener()` existe dans `queue_ws.py` mais **n'est pas branché** dans `main.py`. L'architecture multi-instances (Load Balancer) ne fonctionne pas encore.

### Solution
- `app/websocket/queue_ws.py` — `start_redis_listener()` : utiliser `psubscribe("tonde:events:*")` avec reconnexion automatique
- `app/main.py` — dans `lifespan()` : `asyncio.create_task(ws_manager.start_redis_listener())`

### Canal Pub/Sub
```
tonde:events:{org_id}   → canal par organisation
psubscribe tonde:events:*  → le listener capte toutes les orgs
```

---

## DÉCISION 6 — Rate Limiting sur les endpoints critiques

**Statut :** ✅ Validé — Sprint 1  
**Décidé par :** Vital  
**Lib :** `slowapi==0.1.9` (déjà dans `requirements.txt`)

### Limites

| Endpoint | Limite | Raison |
|---|---|---|
| `POST /auth/login` | 10/minute par IP | Brute force password |
| `POST /auth/register/phone` | 5/minute par IP | Flood SMS |
| `POST /auth/verify-otp` | 5/minute par IP | Brute force OTP |
| `POST /auth/refresh` | 20/minute par IP | Abus de rotation |
| `WebSocket connect` | 10/minute par IP | Flood connexions |

### Impact code
- Créer `app/core/middlewares.py` — configurer `slowapi.Limiter`
- `app/main.py` — `setup_rate_limiting(app)`
- `app/routers/auth.py` — décorateurs `@limiter.limit(...)` sur les routes concernées

---

## DÉCISION 7 — Modèle User Multi-Organisations (Option B)

**Statut :** ✅ Validé — Sprint 2  
**Décidé par :** Vital

### Contexte
Un utilisateur (agent, manager, client VIP) peut appartenir à plusieurs organisations.
Exemple : Jean est agent à la BANCOBU **et** au CHUK.

### Solution retenue : Option B — table `user_organizations`
Ajout d'une table de liaison Many-to-Many en **plus** de la table `employees` existante.

### Structure
```python
class UserOrganization(Base):
    __tablename__ = "user_organizations"
    id: Mapped[str]              # UUID PK
    user_id: Mapped[str]         # FK → users.id
    organization_id: Mapped[str] # FK → organizations.id
    member_number: Mapped[str|None]  # numéro de membre (optionnel)
    status: Mapped[str]          # active | inactive
    created_at: Mapped[datetime]
```

### Note importante
`User.org_id` (champ scalaire actuel) reste présent pour la compatibilité Sprint 1.
La migration complète vers `user_organizations` se fait en Sprint 2 via Alembic.

---

## DÉCISION 8 — Renommage Agency → Branch

**Statut :** 🔜 Prévu — Sprint 2  
**Décidé par :** Vital

### Règle
- `Agency` devient officiellement `Branch` (Filiale / Agence physique)
- `Organization` reste le compte parent (ex : BANCOBU, CHUK)

### Hiérarchie officielle
```
Organization → Branch (ex-Agency) → Service → Counter → Ticket
```

### Action Sprint 2
- Migration Alembic : renommer table `agencies` → `branches`
- Mettre à jour tous les modèles, schémas, services, routers
- Les URLs `/agencies` seront maintenues ou versionnées selon décision Vital

---

## DÉCISION 9 — Feuille de route IA : Échelle de maturité

**Statut :** ✅ Validé — Orientation long terme  
**Décidé par :** Vital

### Progression obligatoire (ne pas brûler les étapes)

```
MVP → Collecte de Données → Analytics → Rules Engine → ML → IA
```

### Phase Rules Engine (avant tout ML)
Avant d'intégrer du Machine Learning, utiliser un moteur de règles métier simple :
```python
if waiting_time > 30:
    trigger_realtime_alert(agency_id)  # Intelligence métier immédiate
```

### Données à collecter dès Sprint 2
- Temps d'attente réels par agence, par service, par heure
- Temps de traitement par agent
- Pics horaires
- Taux d'absence (ABSENT / total CALLED)
- Performances guichet

---

## Ce qui NE change PAS

```
✅ Architecture monolithique modulaire — pas de microservices
✅ Stack technique figée (voir tech.md) — aucune mise à jour sans accord Vital
✅ Pattern Router → Service → Model (toujours)
✅ org_id obligatoire sur toutes les entités métier
✅ Machine à états du ticket (inchangée)
✅ OTP DEV = 123456
✅ JWT : Access 15min / Refresh 7 jours
```
