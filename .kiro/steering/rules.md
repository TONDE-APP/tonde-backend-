# TONDE — Règles de Code et Conventions

## Règles obligatoires

### 1. Async partout

```python
# ✅ TOUJOURS async
async def create_ticket(...) -> TicketResponse:
    result = await db.execute(select(Ticket)...)

# ❌ JAMAIS sync dans FastAPI
def create_ticket(...):
    result = db.execute(...)  # INTERDIT
```

### 2. SQLAlchemy 2.0 uniquement

```python
# ✅ Style 2.0 avec Mapped
class User(Base):
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)

# ❌ Ancien style Column() — INTERDIT
class User(Base):
    id = Column(String, primary_key=True)
```

### 3. Pydantic v2 uniquement

```python
# ✅ Pydantic v2
class CreateTicketRequest(BaseModel):
    agency_id: str
    model_config = ConfigDict(from_attributes=True)

# ❌ Pydantic v1 — INTERDIT
class OldSchema(BaseModel):
    class Config:
        orm_mode = True  # INTERDIT
```

### 4. Logique métier dans les services, jamais dans les routers

```python
# ✅ Router délègue au service
@router.post("")
async def create_ticket(body: CreateTicketRequest, ...):
    service = TicketService(db)
    return await service.create_ticket(body, current_user.id)

# ❌ INTERDIT dans un router
@router.post("")
async def create_ticket(...):
    ticket = Ticket(...)   # logique métier dans router = INTERDIT
    db.add(ticket)
```

### 5. Format de réponse API standard

```python
# ✅ Succès
return {"success": True, "data": result, "message": "OK"}

# ✅ Erreur
raise HTTPException(
    status_code=400,
    detail={"code": "TICKET_EXISTS", "message": "Ticket déjà actif"}
)

# ❌ INTERDIT — retourner un objet ORM brut
return ticket
```

### 6. Typage complet obligatoire

```python
# ✅
async def get_ticket(ticket_id: str, user_id: str, db: AsyncSession) -> TicketResponse:

# ❌ INTERDIT
async def get_ticket(ticket_id, user_id, db):
```

### 7. Docstrings sur chaque méthode de service

```python
async def create_ticket(self, data: CreateTicketRequest, user_id: str) -> TicketResponse:
    """
    Crée un ticket et l'insère dans la file d'attente Redis.

    Args:
        data: Données de création (agency_id, service_id, priority)
        user_id: ID de l'utilisateur connecté

    Returns:
        TicketResponse avec position, ETA et QR token

    Raises:
        HTTPException 400: Si l'agence est fermée
        HTTPException 409: Si un ticket actif existe déjà
    """
```

---

## Multi-tenant — règle absolue

Toute entité contenant des données d'institution **doit** avoir `org_id` :

```python
# ✅ Toujours inclure org_id
class Ticket(Base):
    org_id: Mapped[str] = mapped_column(String(36), index=True)

# ✅ Toujours filtrer par org_id dans les requêtes
result = await db.execute(
    select(Ticket).where(
        Ticket.org_id == current_user.org_id,  # ← OBLIGATOIRE
        Ticket.id == ticket_id,
    )
)
```

---

## RBAC — Rôles et permissions

| Rôle | Permissions |
|------|-------------|
| `client` | Créer ticket, voir ses tickets, payer |
| `agent` | Appeler suivant, gérer son guichet |
| `supervisor` | Stats agence, gérer agents |
| `admin_agency` | Config agence, rapports |
| `admin_org` | Gérer toutes les agences de l'organisation |
| `super_admin` | Accès total (équipe Tonde) |

Toute route protégée vérifie : **token valide + rôle autorisé + org_id correspondant**.

---

## Machine à états des tickets

Transitions strictement autorisées :

```
WAITING   → CALLED       (guichetier appelle)
WAITING   → CANCELLED    (client annule)
CALLED    → SERVING      (client se présente au guichet)
CALLED    → ABSENT       (timeout 3 min sans présentation)
CALLED    → TRANSFERRED
SERVING   → DONE
SERVING   → INCOMPLETE
ABSENT    → WAITING      (client demande à revenir)
```

**Toute transition non listée est INTERDITE.**
Utiliser une machine à états explicite — jamais des `if/else` éparpillés.

---

## Score Redis pour la file d'attente

```python
# Garantit : priorité haute d'abord, puis FIFO dans la même priorité
score = (10 - priority_score) * 1_000_000_000 + int(time.time() * 1000)

# priority_score : emergency=9, vip=5, priority=3, standard=0
```

---

## Environnements

```
DEV     → http://localhost:8000
          (mobile Flutter : http://10.0.2.2:8000 depuis émulateur Android)
STAGING → https://api-staging.tonde.app
PROD    → https://api.tonde.app
```

---

## Contexte business

```
Fondateur / Tech Lead : Vital
Produit               : SaaS B2B Queue Management
Marché V1             : Burundi (Bujumbura)
Marché V1.5           : RDC (Goma, Bukavu)
Marché V2+            : Afrique de l'Est & Centrale
Secteurs V1           : Banques + Hôpitaux
Monnaie               : BIF (Franc Burundais)
OTP test DEV          : 123456
GitHub org            : tonde-app
Repos                 : tonde-backend · tonde-mobile · tonde-web · tonde-docs
```

---

## Ce qu'il ne faut jamais faire

```
❌ Logique métier dans les routers
❌ Appels DB directs dans les routers
❌ Style SQLAlchemy 1.x (Column, Session sync)
❌ Pydantic v1 (orm_mode, validator sans @classmethod)
❌ Queries sans filtre org_id sur les données multi-tenant
❌ Transitions de statut ticket non autorisées
❌ Supposer que la connexion client est stable (Offline First)
❌ Microservices — le MVP est monolithique
❌ Refonte massive sans plan validé par Vital
❌ Code sans typage complet
❌ Méthode de service sans docstring
❌ Retourner des objets ORM bruts (toujours passer par les schemas)
```
