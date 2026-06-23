# S2-08 — Tasks

## Tâches d'implémentation

### 1. Ajouter champs à Organization
**Fichier :** `app/models/organization.py`

```python
invitation_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
invitation_expires_at: Mapped[datetime | None] = nullable=True)
invitation_code_active: Mapped[bool] = mapped_column(Boolean, default=False)
```

**Migration Alembic :**
```bash
alembic revision --autogenerate -m "add_invitation_code_to_organizations"
```

### 2. Créer le Schema
**Fichier :** `app/schemas/organization.py`

```python
class JoinByCodeRequest(BaseModel):
    code: str  # ex: "BANCOBU-2026"

class OrganizationMemberResponse(BaseModel):
    id: str
    name: str
    slug: str
    role: str  # "client" par défaut
```

### 3. Ajouter au Service
**Fichier :** `app/services/organization_service.py`

```python
async def join_by_code(self, user_id: str, code: str) -> dict:
    """Rejoindre une org via code d'invitation."""
    
async def get_user_organizations(self, user_id: str) -> list[OrganizationMemberResponse]:
    """Lister les orgs d'un user."""

async def leave_organization(self, user_id: str, org_id: str) -> dict:
    """Quitter une organisation."""

async def generate_invitation_code(self, org_id: str) -> dict:
    """Générer/régénérer le code d'invitation."""
```

### 4. Ajouter au Router
**Fichier :** `app/routers/organizations.py`

```python
@router.post("/users/me/organizations/join", ...)
async def join_by_code(body: JoinByCodeRequest, current_user: User = Depends(...)):
    return await service.join_by_code(current_user.id, body.code)

@router.get("/users/me/organizations", ...)
async def list_my_organizations(current_user: User = Depends(...)):
    return await service.get_user_organizations(current_user.id)

@router.delete("/users/me/organizations/{org_id}", ...)
async def leave_organization(org_id: str, current_user: User = Depends(...)):
    return await service.leave_organization(current_user.id, org_id)

# Admin endpoint pour générer le code
@router.post("/{org_id}/invitation-code", ...)
async def generate_invitation_code(org_id: str, ...):
    return await service.generate_invitation_code(org_id)
```

## Tests à écrire

```python
test_join_by_valid_code
test_join_by_invalid_code_fails
test_join_by_expired_code_fails
test_join_when_already_member_fails
test_list_user_organizations
test_leave_organization
test_generate_invitation_code
test_invitation_code_expires
```

## Checklist PR

- [ ] Champs ajoutés au modèle Organization
- [ ] Migration Alembic créée
- [ ] Schemas ajoutés
- [ ] Service mis à jour
- [ ] Endpoints créés
- [ ] Validateur code expiré
- [ ] Validateur déjà membre
- [ ] Tests passent
