# Requirements Document — TASK-04 : Clés Redis segmentées par service

## Introduction

Dans l'architecture actuelle de TONDE, toutes les files d'attente Redis d'une agence partagent une clé unique `tonde:{org_id}:{agency_id}:queue`. Cette architecture ne permet pas à plusieurs services (Caisse, Crédit, Conseiller, VIP) de coexister dans la même agence avec des files indépendantes.

Cette feature introduit `service_id` comme troisième segment de la clé Redis, conformément à la **DÉCISION 4** validée par Vital. Le changement est purement structurel (clés Redis + propagation de `service_id`) : aucune migration de base de données n'est requise car `service_id` est déjà présent sur le modèle `Ticket`.

## Glossaire

- **Queue_Key** : clé Redis de type Sorted Set identifiant la file d'attente d'un service dans une agence.
- **Redis_Queue** : file d'attente Redis implémentée sous forme de Sorted Set (`ZADD`, `ZRANK`, `ZCARD`, `ZRANGE`, `ZREM`).
- **Service** : entité métier représentant un guichet logique (Caisse, Crédit, Conseiller, VIP) appartenant à une agence.
- **Ticket_Service** : couche service Python (`app/services/ticket_service.py`) orchestrant la création, l'appel, l'annulation et le retour en file des tickets.
- **Redis_Module** : module Python `app/core/redis.py` centralisant tous les helpers d'accès à Redis.
- **CallNextRequest** : schéma Pydantic v2 (`app/schemas/ticket.py`) transportant la requête du guichetier pour appeler le prochain ticket.
- **org_id** : identifiant d'organisation — garantit l'isolation multi-tenant.
- **agency_id** : identifiant d'agence — premier niveau de segmentation intra-organisation.
- **service_id** : identifiant de service — nouveau deuxième niveau de segmentation intra-agence.

---

## Requirements

### Requirement 1 : Nouvelle structure de la clé Redis

**User Story :** En tant que développeur, je veux que chaque service d'une agence possède sa propre file Redis, afin que les tickets de la Caisse, du Crédit et du Conseiller ne soient jamais mélangés.

#### Acceptance Criteria

1. THE Queue_Key SHALL follow the format `tonde:{org_id}:{agency_id}:{service_id}:queue`.
2. WHEN `_queue_key()` is called with `org_id`, `agency_id`, and `service_id`, THE Redis_Module SHALL return a string matching `tonde:{org_id}:{agency_id}:{service_id}:queue` exactly.
3. IF `service_id` is absent from a call to any Redis queue function, THEN THE Redis_Module SHALL raise a `TypeError` at call time.

---

### Requirement 2 : Mise à jour de la signature des fonctions Redis de file

**User Story :** En tant que développeur, je veux que toutes les fonctions de gestion de file acceptent `service_id`, afin que les opérations soient toujours dirigées vers la file correcte.

#### Acceptance Criteria

1. THE Redis_Module SHALL accept `service_id: str` as a mandatory parameter in `add_to_queue(org_id, agency_id, service_id, ticket_id, priority)`.
2. THE Redis_Module SHALL accept `service_id: str` as a mandatory parameter in `get_queue_position(org_id, agency_id, service_id, ticket_id)`.
3. THE Redis_Module SHALL accept `service_id: str` as a mandatory parameter in `get_queue_size(org_id, agency_id, service_id)`.
4. THE Redis_Module SHALL accept `service_id: str` as a mandatory parameter in `remove_from_queue(org_id, agency_id, service_id, ticket_id)`.
5. THE Redis_Module SHALL accept `service_id: str` as a mandatory parameter in `get_next_ticket(org_id, agency_id, service_id)`.
6. THE Redis_Module SHALL accept `service_id: str` as a mandatory parameter in `get_queue_snapshot(org_id, agency_id, service_id)`.
7. WHEN two tickets from different services are added to the same agency queue, THE Redis_Module SHALL store them in separate Sorted Sets identified by their respective `service_id`.

---

### Requirement 3 : Propagation de `service_id` dans le Ticket_Service

**User Story :** En tant que système, je veux que chaque opération sur la file passe le `service_id` du ticket, afin que la bonne file Redis soit ciblée à chaque étape du cycle de vie du ticket.

#### Acceptance Criteria

1. WHEN `create_ticket()` is called, THE Ticket_Service SHALL pass `data.service_id` to `add_to_queue()` and `get_queue_size()`.
2. WHEN `get_ticket()` is called, THE Ticket_Service SHALL pass `ticket.service_id` to `get_queue_position()` and `get_queue_size()`.
3. WHEN `cancel_ticket()` is called, THE Ticket_Service SHALL pass `ticket.service_id` to `remove_from_queue()`.
4. WHEN `call_next()` is called, THE Ticket_Service SHALL pass `service_id` received from the request body to `get_next_ticket()` and `remove_from_queue()`.
5. WHEN `return_to_queue()` is called, THE Ticket_Service SHALL pass `ticket.service_id` to `add_to_queue()`.

---

### Requirement 4 : Ajout de `service_id` dans `CallNextRequest`

**User Story :** En tant que guichetier, je veux indiquer le service dont je gère la file lors de l'appel du prochain ticket, afin d'appeler uniquement les tickets du bon service.

#### Acceptance Criteria

1. THE CallNextRequest schema SHALL include `service_id: str` as a mandatory field.
2. WHEN `CallNextRequest` is instantiated without `service_id`, THE CallNextRequest SHALL raise a `ValidationError`.
3. WHEN the router endpoint `POST /counter/call-next` receives a `CallNextRequest`, THE router SHALL forward `body.service_id` to `TicketService.call_next()`.

---

### Requirement 5 : Isolation des files par service

**User Story :** En tant qu'architecte, je veux que deux services différents d'une même agence aient des files Redis totalement indépendantes, afin qu'un appel sur le service Caisse n'affecte jamais la file du service Crédit.

#### Acceptance Criteria

1. WHEN a ticket is added to service A and a ticket is added to service B in the same agency, THE Redis_Module SHALL store them under different Sorted Set keys.
2. WHEN `get_next_ticket()` is called for service A, THE Redis_Module SHALL return only tickets belonging to service A's queue.
3. WHEN `remove_from_queue()` is called for a ticket in service A's queue, THE Redis_Module SHALL not affect service B's queue.
4. WHEN `get_queue_size()` is called for service A, THE Redis_Module SHALL return the count of tickets in service A's queue only, excluding tickets from any other service.

---

### Requirement 6 : Non-régression des tests existants

**User Story :** En tant que développeur, je veux que les tests unitaires existants soient mis à jour pour refléter les nouvelles signatures, afin que la suite de tests reste verte après le changement.

#### Acceptance Criteria

1. WHEN the test suite runs after the change, THE test suite SHALL pass without errors related to incorrect Redis mock signatures.
2. THE mock fixture `mock_queue` in `tests/test_ticket_service.py` SHALL mock all six Redis queue functions with their updated `service_id` parameter.
3. WHEN new tests for TASK-04 are added, THE test suite SHALL include `test_queue_key_includes_service_id`, `test_two_services_have_independent_queues`, `test_call_next_targets_correct_service_queue`, and `test_cancel_removes_from_correct_service_queue`.
