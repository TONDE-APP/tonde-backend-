# S2-07 — Services CRUD

## Contexte

Le MVP actuelle ne permet pas aux clients mobiles de :
- Voir les services disponibles dans une agence
- Choisir un service lors de la création d'un ticket

Or `POST /api/v1/tickets` exige `service_id`. Sans endpoint pour lister les services, le client mobile ne peut pas fonctionner.

## Objectif

Créer le module CRUD complet pour les Services (Caisse, Crédit, Consultation, etc.).

## Scope

### Endpoints à créer

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/v1/organizations/{org_id}/agencies/{agency_id}/services` | Créer un service |
| GET | `/api/v1/organizations/{org_id}/agencies/{agency_id}/services` | Lister les services (admin) |
| GET | `/api/v1/agencies/{agency_id}/services` | Lister les services (public — mobile) |
| GET | `/api/v1/agencies/{agency_id}/services/{service_id}` | Détail d'un service |
| PATCH | `/api/v1/organizations/{org_id}/agencies/{agency_id}/services/{service_id}` | Modifier un service |
| DELETE | `/api/v1/organizations/{org_id}/agencies/{agency_id}/services/{service_id}` | Supprimer un service |

### Modèle Service (existant dans agency.py)

Le modèle `Service` existe déjà dans `app/models/agency.py`. Il contient :
- `id`, `org_id`, `agency_id`
- `name`, `description`
- `ticket_prefix` (A, B, C...)
- `avg_duration_minutes`
- `is_active`

### Permissions RBAC

| Rôle | Permissions |
|------|-------------|
| ADMIN_ORG | CRUD complet sur tous les services de l'org |
| ADMIN_AGENCY | CRUD sur les services de son agence |
| CLIENT | Lecture seule (via endpoint public) |

## Contraintes

1. Un service doit appartenir à une agence
2. Le `ticket_prefix` doit être unique par agence
3. On ne peut pas supprimer un service avec des tickets actifs

## Impact

- Endpoint public `/agencies/{id}/services` permet au mobile de peupler le sélecteur de service
- Le client mobile peut maintenant prendre un ticket en choisissant un service
