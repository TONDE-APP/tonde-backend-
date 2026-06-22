# Implementation Plan : TASK-04 — Clés Redis segmentées par service

## Overview

Ce plan implémente la DÉCISION 4 en propageant `service_id` dans toutes les fonctions Redis de file, puis en cascadant ce changement dans la couche service, les schémas Pydantic et le router. L'ordre des tâches garantit qu'aucun code n'est laissé orphelin : on commence par la fondation (clé Redis), puis on remonte la pile couche par couche.

Branche Git : `feat/redis-queue-key-by-service`

## Tasks

- [ ] 1. Mettre à jour `_queue_key()` et les 6 fonctions de file dans `app/core/redis.py`
  - Ajouter `service_id: str` comme troisième paramètre obligatoire (sans valeur par défaut) à `_queue_key(org_id, agency_id, service_id)`
  - Mettre à jour la f-string : `f"tonde:{org_id}:{agency_id}:{service_id}:queue"`
  - Mettre à jour la signature et l'appel interne à `_queue_key()` dans chacune des 6 fonctions : `add_to_queue`, `get_queue_position`, `get_queue_size`, `remove_from_queue`, `get_next_ticket`, `get_queue_snapshot`
  - Mettre à jour les docstrings de chaque fonction pour documenter le nouveau paramètre `service_id`
  - Mettre à jour le commentaire de convention des clés Redis en tête de fichier
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 1.1 Écrire les tests property-based pour `_queue_key()`
    - **Property 1 : Format de la clé Redis**
    - Utiliser `hypothesis` : `@given(org_id=text(min_size=1), agency_id=text(min_size=1), service_id=text(min_size=1))`
    - Asserter que le résultat vaut exactement `f"tonde:{org_id}:{agency_id}:{service_id}:queue"`
    - `@settings(max_examples=100)`
    - Annoter : `# Feature: sprint1-task04-redis-queue-key, Property 1: Queue key format`
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 1.2 Écrire le test property-based d'isolation des files
    - **Property 2 : Isolation des files par service**
    - Utiliser `hypothesis` : `@given(org_id=text(min_size=1), agency_id=text(min_size=1), service_id_a=text(min_size=1), service_id_b=text(min_size=1))`
    - Utiliser `assume(service_id_a != service_id_b)` pour garantir des services distincts
    - Asserter que `_queue_key(org, agency, svc_a) != _queue_key(org, agency, svc_b)`
    - `@settings(max_examples=100)`
    - Annoter : `# Feature: sprint1-task04-redis-queue-key, Property 2: Key isolation`
    - **Validates: Requirements 2.7, 5.1, 5.3**

- [ ] 2. Mettre à jour `app/schemas/ticket.py` — ajouter `service_id` à `CallNextRequest`
  - Ajouter le champ `service_id: str` comme attribut obligatoire dans `CallNextRequest`
  - Placer le champ après `agency_id` pour maintenir la cohérence avec les autres schémas
  - _Requirements: 4.1, 4.2_

  - [ ]* 2.1 Écrire le test unitaire pour `CallNextRequest`
    - `test_callnextrequest_requires_service_id` : instancier `CallNextRequest(agency_id="a", counter_id="c", counter_name="G1")` sans `service_id` et asserter que Pydantic lève `ValidationError`
    - `test_callnextrequest_valid_with_service_id` : instancier avec tous les champs et asserter que `service_id` est bien accessible
    - _Requirements: 4.1, 4.2_

- [ ] 3. Mettre à jour `app/services/ticket_service.py` — propager `service_id` dans tous les appels Redis
  - `create_ticket()` : passer `data.service_id` à `add_to_queue()` et `get_queue_size()`
  - `get_ticket()` : passer `ticket.service_id` à `get_queue_position()` et `get_queue_size()`
  - `cancel_ticket()` : passer `ticket.service_id` à `remove_from_queue()`
  - `call_next()` : ajouter `service_id: str` comme nouveau paramètre de la méthode; passer `service_id` à `get_next_ticket()` et `remove_from_queue()`
  - `return_to_queue()` : passer `ticket.service_id` à `add_to_queue()`
  - Mettre à jour la docstring de `call_next()` pour documenter le nouveau paramètre
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 3.1 Écrire les tests unitaires de forwarding `service_id`
    - `test_create_ticket_passes_service_id_to_redis` : créer un ticket et inspecter `add_to_queue.call_args` pour vérifier que `service_id` est bien passé
    - `test_cancel_ticket_passes_service_id_to_remove_from_queue` : annuler et inspecter `remove_from_queue.call_args`
    - Utiliser les fixtures existantes `ticket_service`, `db_session`, `mock_queue`
    - _Requirements: 3.1, 3.3_

- [ ] 4. Mettre à jour `app/routers/tickets.py` — passer `service_id` à `call_next`
  - Dans l'endpoint `POST /counter/call-next`, ajouter `service_id=body.service_id` dans l'appel `service.call_next(...)`
  - _Requirements: 4.3_

  - [ ]* 4.1 Écrire le test unitaire du router `call_next`
    - `test_call_next_targets_correct_service_queue` : mocker `TicketService.call_next` et vérifier que `call_next` a été appelé avec le `service_id` du body
    - _Requirements: 4.3_

- [ ] 5. Mettre à jour la fixture `mock_queue` dans `tests/test_ticket_service.py`
  - Vérifier que tous les tests existants (création, annulation, machine à états) passent toujours avec les nouveaux mocks
  - La fixture `mock_queue` reste structurellement identique car `AsyncMock` accepte n'importe quelle signature — s'assurer que les tests qui vérifient les arguments d'appel (`call_args`) assertent désormais la présence de `service_id`
  - _Requirements: 6.1, 6.2_

  - [ ]* 5.1 Écrire les 4 tests spécifiques TASK-04
    - `test_queue_key_includes_service_id` : appel direct à `_queue_key("org1", "agency1", "svc1")` et assertion du format
    - `test_two_services_have_independent_queues` : vérifier que deux `service_id` distincts produisent des clés distinctes
    - `test_call_next_targets_correct_service_queue` : `call_next` appelle `get_next_ticket` avec le bon `service_id`
    - `test_cancel_removes_from_correct_service_queue` : `cancel_ticket` appelle `remove_from_queue` avec `ticket.service_id`
    - _Requirements: 6.3_

- [ ] 6. Checkpoint — vérifier que tous les tests passent
  - Lancer `pytest tests/ -v --tb=short` et s'assurer que la suite est verte
  - Vérifier qu'aucun `TypeError` lié aux nouvelles signatures n'est levé
  - Assurer que tous les tests d'intégration existants (`test_create_ticket_success`, `test_cancel_ticket_success`, etc.) passent toujours
  - Demander à l'utilisateur si des questions se posent avant de considérer la tâche terminée.

## Notes

- Les tâches marquées `*` sont optionnelles pour un MVP rapide, mais fortement recommandées (règle de qualité TONDE)
- Aucune migration Alembic n'est requise — `Ticket.service_id` existe déjà en base
- L'ordre d'implémentation est critique : `redis.py` en premier, puis `schemas`, puis `services`, puis `router` — inverser l'ordre laisserait du code cassé temporairement
- `hypothesis` doit être installé si absent : `pip install hypothesis` (à ajouter dans `requirements.txt` section dev ou directement)
- Branche Git : `feat/redis-queue-key-by-service` — aucun push direct sur `main`
