# S2-08 — Design Technique

## Architecture

```
app/
├── models/
│   └── organization.py           # Ajouter invitation_code, etc.
├── schemas/
│   └── organization.py           # JoinByCodeRequest, OrganizationMemberResponse
├── services/
│   └── organization_service.py   # Ajouter join_by_code(), etc.
└── routers/
    └── organizations.py           # Ajouter /users/me/organizations/...
```

## Modèle Invitation (extension Organization)

```python
# Dans Organization
invitation_code: Mapped[str | None]  # Code d'invitation (ex: "BANCOBU-2026")
invitation_expires_at: Mapped[datetime | None]  # Expiration du code
```

## Schéma des endpoints

### POST /api/v1/users/me/organizations/join

**Auth :** Bearer token requis
**Body :**
```json
{
    "code": "BANCOBU-2026"
}
```

**Response 200 :**
```json
{
    "success": true,
    "message": "Vous avez rejoint BANCOBU",
    "organization": {
        "id": "uuid",
        "name": "BANCOBU",
        "slug": "bancobu"
    }
}
```

**Errors :**
- 400 : Code invalide ou expiré
- 409 : Déjà membre de cette organisation

### GET /api/v1/users/me/organizations

**Auth :** Bearer token requis
**Response 200 :**
```json
[
    {
        "id": "uuid-1",
        "name": "BANCOBU",
        "slug": "bancobu",
        "role": "client"
    },
    {
        "id": "uuid-2",
        "name": "CHUK",
        "slug": "chuk",
        "role": "client"
    }
]
```

## Points à traiter

1. **Génération du code** : admin peut générer/régénérer le code
2. **Expiration** : 30 jours par défaut
3. **User organizations table** : dépend de S2-02
4. **Un seul org_id dans User** : Pour l'instant, garder `User.org_id` pour compatibilité
