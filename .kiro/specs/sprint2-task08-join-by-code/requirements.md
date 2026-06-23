# S2-08 — Join by Code

## Contexte

TONDE est une plateforme multi-organisations. Un utilisateur peut appartenir à plusieurs organisations (BANCOBU, CHUK, etc.).

Actuellement, un client OTP a `org_id = NULL`. Il ne peut pas :
- Rejoindre une organisation
- Prendre un ticket dans une agence spécifique

## Objectif

Permettre à un utilisateur de rejoindre une organisation via un code d'invitation.

## Sources

Ce module est décrit dans `.kiro/skills/01_user_membership_model.md` :
> **Niveau 1 : Code d'invitation**
> L'organisation fournit un code. Exemple : `BANCOBU-2026`
> L'utilisateur saisit ce code. TONDE vérifie le code.
> Si valide : l'utilisateur devient membre de l'organisation.

## Scope

### Endpoints à créer

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/v1/users/me/organizations/join` | Rejoindre via code |
| GET | `/api/v1/users/me/organizations` | Lister mes organisations |
| DELETE | `/api/v1/users/me/organizations/{org_id}` | Quitter une organisation |

### Table user_organizations (S2-02)

Cette task dépend de **S2-02** qui crée la table `user_organizations`.

### Flux

```
1. Admin crée un code d'invitation (ex: BANCOBU-2026)
2. Code stocké en DB avec org_id
3. Client mobile saisit le code
4. Backend vérifie le code
5. Si valide : insertion dans user_organizations
6. User peut maintenant voir BANCOBU dans sa liste d'organisations
```

## Permissions

- Tout utilisateur connecté peut rejoindre une organisation via code
- Le code doit être valide et non expiré
- Un user ne peut pas rejoindre 2x la même org

## Contraintes

1. Code sensible à la casse (stocker en uppercase)
2. Code avec expiration (ex: 30 jours)
3. Code à usage unique ou multi-usage (configurable)
4. Ne pas permettre de rejoindre si déjà membre
