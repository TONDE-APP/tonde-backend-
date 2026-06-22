# Design Document — TASK-03 : Règle "1 ticket actif global"

## Overview

Ce correctif modifie deux méthodes dans `app/services/ticket_service.py` pour appliquer
la règle validée en DÉCISION 1 : **un seul ticket actif par utilisateur, sur toute la
plateforme**, sans restriction par agence.

**Changements de surface minimale** (two files, zero new models, zero migrations) :

| Élément | Avant | Après |
|---|---|---|
| `_get_active_ticket(user_id, agency_id)` | filtre `agency_id` + 3 statuts | sans `agency_id` + 6 statuts |
| Réponse 409 | `code: TICKET_EXISTS` | `code: TICKET_ALREADY_ACTIVE` + `active_ticket_id` + `active_ticket_number` |
| Constante | aucune | `ACTIVE_STATUSES` au niveau module |

---

## Architecture

Le fix s'inscrit entièrement dans la couche **Service** du pattern `Router → Service → Model`.
Aucun changement de routeur, aucun changement de schéma Pydantic, aucune migration Alembic.

```
Router (inchangé)
    │
    ▼
TicketService.create_ticket()          ← point d'entrée de la règle
    │
    ├── _get_active_ticket(user_id)    ← seul changement de logique
    │       │
    │       └── SELECT * FROM tickets
    │           WHERE user_id = ?
    │             AND status IN (ACTIVE_STATUSES)   ← sans agency_id
    │
    └── HTTP 409 enrichi si ticket trouvé
```

---

## Components and Interfaces

### Constante `ACTIVE_STATUSES` (nouveau, niveau module)

```python
# app/services/ticket_service.py — ajout en tête de fichier (après les imports)
ACTIVE_STATUSES: list[TicketStatus] = [
    TicketStatus.WAITING,
    TicketStatus.CALLED,
    TicketStatus.SERVING,
    TicketStatus.ABSENT,
    TicketStatus.TRANSFERRED,
    TicketStatus.INCOMPLETE,
]
```

Placée au niveau du module (et non dans la classe) pour permettre son import direct dans
les tests sans instancier `TicketService`.

### `_get_active_ticket()` — nouvelle signature

```python
async def _get_active_ticket(self, user_id: str) -> Ticket | None:
    """
    Vérifie si l'utilisateur possède un ticket actif sur toute la plateforme.

    La vérification est globale : aucun filtre sur agency_id.
    Les statuts actifs sont définis par ACTIVE_STATUSES.

    Args:
        user_id: ID de l'utilisateur à vérifier.

    Returns:
        Le ticket actif trouvé, ou None si l'utilisateur est libre.
    """
    result = await self.db.execute(
        select(Ticket).where(
            Ticket.user_id == user_id,
            Ticket.status.in_(ACTIVE_STATUSES),
        )
    )
    return result.scalar_one_or_none()
```

### `create_ticket()` — appel mis à jour + réponse 409 enrichie

```python
# Dans create_ticket(), remplacer :
existing = await self._get_active_ticket(user_id, data.agency_id)
if existing:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "TICKET_EXISTS", "message": "..."},
    )

# Par :
existing = await self._get_active_ticket(user_id)
if existing:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "TICKET_ALREADY_ACTIVE",
            "message": (
                f"Vous avez déjà un ticket actif ({existing.number} — "
                f"statut : {existing.status.value}). "
                "Attendez qu'il soit terminé ou annulez-le."
            ),
            "active_ticket_id": existing.id,
            "active_ticket_number": existing.number,
        },
    )
```

---

## Data Models

Aucun changement de schéma de base de données. La table `tickets` existante supporte déjà
tous les statuts requis (cf. `TicketStatus` dans `app/models/ticket.py`).

Les colonnes utilisées par la requête modifiée sont :

| Colonne | Type | Index existant |
|---|---|---|
| `user_id` | `String(36)` | Non (acceptable pour MVP, à indexer si perf dégradée) |
| `status` | `SAEnum(TicketStatus)` | Non |

> Note de performance : pour les volumes MVP (Burundi, ~50 agences, ~1 000 tickets/jour),
> l'absence d'index composite `(user_id, status)` est acceptable. Prévoir un index en
> Sprint 2 si les métriques P99 dépassent 200 ms sur cette requête.

---

## Correctness Properties

*Une propriété est une caractéristique ou un comportement qui doit rester vrai pour toutes
les exécutions valides du système — une spécification formelle de ce que le logiciel doit
faire. Les propriétés servent de pont entre les spécifications lisibles par l'humain et
les garanties de correction vérifiables par la machine.*

### Property 1 : Tout statut actif bloque la création

*Pour tout* utilisateur possédant un ticket dont le statut appartient à `ACTIVE_STATUSES`
(WAITING, CALLED, SERVING, ABSENT, TRANSFERRED, INCOMPLETE), tenter de créer un nouveau
ticket doit produire une `HTTPException` avec `status_code == 409`.

**Validates: Requirements 1.2, 4.1, 4.3**

### Property 2 : Tout statut terminal libère la création

*Pour tout* utilisateur dont le dernier ticket est en statut `DONE` ou `CANCELLED`,
la création d'un nouveau ticket doit réussir sans lever d'exception 409.

**Validates: Requirements 1.3, 5.1, 5.2, 5.3**

### Property 3 : La réponse 409 contient les champs de redirection mobile

*Pour tout* ticket actif existant, la `HTTPException` 409 levée par `create_ticket()`
doit contenir un `detail` avec les champs `code == "TICKET_ALREADY_ACTIVE"`,
`active_ticket_id == existing.id`, et `active_ticket_number == existing.number`.

**Validates: Requirements 1.4, 3.1, 3.2, 3.3, 3.4, 3.5**

### Property 4 : Détection sans filtre agence

*Pour tout* utilisateur avec un ticket actif dans n'importe quelle agence A1,
`_get_active_ticket(user_id)` (sans `agency_id`) doit retourner ce ticket même si une
agence différente A2 est utilisée lors de la tentative de création.

**Validates: Requirements 1.1, 2.1, 2.2**

---

## Error Handling

| Situation | Code HTTP | `code` dans detail | Champs supplémentaires |
|---|---|---|---|
| Ticket actif existant | 409 | `TICKET_ALREADY_ACTIVE` | `active_ticket_id`, `active_ticket_number` |
| Agence fermée | 400 | `AGENCY_CLOSED` | — (inchangé) |
| Agence introuvable | 404 | `AGENCY_NOT_FOUND` | — (inchangé) |
| Service introuvable | 404 | `SERVICE_NOT_FOUND` | — (inchangé) |
| Transition interdite | 400 | `INVALID_TRANSITION` | — (inchangé) |

Le code existant `TICKET_EXISTS` est **remplacé** par `TICKET_ALREADY_ACTIVE` pour être
cohérent avec le nom dans la DÉCISION 1 et pour éviter la confusion avec une future
validation de doublon de numéro.

---

## Testing Strategy

### Approche duale

- **Tests unitaires** : vérifications d'exemples spécifiques (cas nominal, isolation agence)
- **Tests de propriétés** : vérifications universelles paramétriques (tous les statuts actifs,
  tous les statuts terminaux)

Cette tâche est **appropriée pour les property-based tests** car :
- La logique de filtrage varie de manière significative selon le statut du ticket
- 100 itérations couvrent des combinaisons de `user_id`, `agency_id`, et `TicketStatus`
  impossibles à écrire manuellement
- Les fonctions testées sont pures (pas d'appels AWS, pas de services externes coûteux)

### Librairie PBT retenue

**`hypothesis`** (déjà utilisable avec `pytest-asyncio`) avec des stratégies
personnalisées pour générer des `TicketStatus` aléatoires.

```python
from hypothesis import given, settings
from hypothesis import strategies as st

# Stratégies réutilisables
active_status_strategy = st.sampled_from(ACTIVE_STATUSES)
terminal_status_strategy = st.sampled_from([TicketStatus.DONE, TicketStatus.CANCELLED])
```

### Configuration des tests de propriétés

- Minimum **100 itérations** par test de propriété (`@settings(max_examples=100)`)
- Tag de référence : `Feature: sprint1-task03-one-active-ticket, Property N: <texte>`
- Chaque test de propriété correspond à **exactement une propriété** du design

### Plan de tests

| Test | Type | Propriété validée |
|---|---|---|
| `test_active_statuses_constant` | Unit | Req 1.5 — contenu exact de `ACTIVE_STATUSES` |
| `test_any_active_status_blocks_creation` | Property | Property 1 |
| `test_terminal_statuses_allow_creation` | Property | Property 2 |
| `test_409_contains_redirect_fields` | Property | Property 3 |
| `test_detection_ignores_agency_id` | Property | Property 4 |
| `test_ticket_blocked_different_agency` | Unit | Scénario BANCOBU → CHUK |
| `test_absent_ticket_blocks_new_ticket` | Unit | Edge case ABSENT explicite |
| `test_transferred_ticket_blocks_new_ticket` | Unit | Edge case TRANSFERRED explicite |
| `test_409_includes_active_ticket_id` | Unit | Vérification exacte des champs 409 |

### Tests unitaires : couverture des appels à conserver

Les tests existants dans `test_ticket_service.py` qui testent `test_create_ticket_duplicate_raises_409`
doivent être mis à jour pour vérifier `code == "TICKET_ALREADY_ACTIVE"` au lieu de
`code == "TICKET_EXISTS"`.
