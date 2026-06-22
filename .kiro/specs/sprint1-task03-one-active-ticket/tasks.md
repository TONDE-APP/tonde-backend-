# Implementation Plan — TASK-03 : Règle "1 ticket actif global"

## Overview

Correction minimale dans `app/services/ticket_service.py` :
1. Ajouter la constante `ACTIVE_STATUSES` au niveau module
2. Modifier `_get_active_ticket()` pour supprimer le filtre `agency_id` et étendre les statuts
3. Mettre à jour `create_ticket()` pour utiliser la nouvelle signature et enrichir la 409
4. Mettre à jour les tests existants + écrire les nouveaux tests

Branche Git : `fix/one-active-ticket-global`

---

## Tasks

- [ ] 1. Ajouter la constante `ACTIVE_STATUSES` dans `ticket_service.py`
  - Déclarer `ACTIVE_STATUSES: list[TicketStatus]` au niveau module, juste après les imports,
    avec exactement les statuts : `WAITING`, `CALLED`, `SERVING`, `ABSENT`, `TRANSFERRED`,
    `INCOMPLETE`
  - S'assurer que la constante est importable directement (`from app.services.ticket_service import ACTIVE_STATUSES`)
  - _Requirements: 1.5_

- [ ] 2. Modifier `_get_active_ticket()` pour appliquer la règle globale
  - [ ] 2.1 Supprimer le paramètre `agency_id` de la signature de la méthode
    - Nouvelle signature : `async def _get_active_ticket(self, user_id: str) -> Ticket | None:`
    - Mettre à jour la docstring pour refléter la vérification globale sans filtre agence
    - _Requirements: 2.1, 2.2_

  - [ ] 2.2 Réécrire la requête SQLAlchemy dans `_get_active_ticket()`
    - Supprimer le `.where(Ticket.agency_id == agency_id, ...)` de la requête
    - Remplacer les 3 statuts par `Ticket.status.in_(ACTIVE_STATUSES)`
    - Vérifier que `scalar_one_or_none()` est toujours utilisé (gestion du cas None)
    - _Requirements: 2.2, 2.4, 2.5_

  - [ ] 2.3 Mettre à jour l'appel à `_get_active_ticket()` dans `create_ticket()`
    - Remplacer `await self._get_active_ticket(user_id, data.agency_id)` par
      `await self._get_active_ticket(user_id)`
    - _Requirements: 2.3_

- [ ] 3. Enrichir la réponse HTTP 409 dans `create_ticket()`
  - Remplacer l'`HTTPException` existante (code `TICKET_EXISTS`) par la nouvelle structure :
    ```python
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
  - Vérifier que `existing` est bien l'objet `Ticket` retourné par `_get_active_ticket()`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 4. Checkpoint — vérification intermédiaire
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Mettre à jour le test existant `test_create_ticket_duplicate_raises_409`
  - Changer l'assertion `exc_info.value.detail["code"] == "TICKET_EXISTS"` en
    `exc_info.value.detail["code"] == "TICKET_ALREADY_ACTIVE"`
  - Ajouter des assertions sur `active_ticket_id` et `active_ticket_number` dans le detail
  - _Requirements: 3.1, 3.4, 3.5_

- [ ] 6. Écrire les nouveaux tests unitaires dans `tests/test_ticket_service.py`
  - [ ] 6.1 `test_ticket_blocked_different_agency`
    - Créer deux agences dans la même org (simulant BANCOBU et CHUK)
    - Créer un ticket `WAITING` dans l'agence A pour `user_id`
    - Tenter de créer un ticket dans l'agence B pour le même `user_id`
    - Vérifier : HTTP 409, `code == "TICKET_ALREADY_ACTIVE"`
    - _Requirements: 1.1, 1.2_

  - [ ] 6.2 `test_ticket_allowed_after_done`
    - Créer un ticket, le faire passer en `DONE` via la machine à états
      (`WAITING → CALLED → SERVING → DONE`)
    - Créer un second ticket pour le même `user_id`
    - Vérifier : succès (pas de 409)
    - _Requirements: 1.3, 5.1_

  - [ ] 6.3 `test_ticket_allowed_after_cancel`
    - Créer un ticket `WAITING`, l'annuler avec `cancel_ticket()`
    - Créer un second ticket pour le même `user_id`
    - Vérifier : succès (pas de 409)
    - _Requirements: 1.3, 5.2_

  - [ ] 6.4 `test_absent_ticket_blocks_new_ticket`
    - Créer un ticket, le faire passer en `ABSENT` (`WAITING → CALLED → ABSENT`)
    - Tenter de créer un second ticket pour le même `user_id`
    - Vérifier : HTTP 409
    - _Requirements: 1.2, 4.1_

  - [ ] 6.5 `test_transferred_ticket_blocks_new_ticket`
    - Manipuler directement le statut d'un ticket en `TRANSFERRED` (via `_transition()`)
    - Tenter de créer un second ticket pour le même `user_id`
    - Vérifier : HTTP 409
    - _Requirements: 1.2, 4.3_

  - [ ] 6.6 `test_409_includes_active_ticket_id`
    - Créer un ticket `WAITING`, noter son `id` et son `number`
    - Tenter d'en créer un second
    - Vérifier : `detail["active_ticket_id"] == premier_ticket.id`
    - Vérifier : `detail["active_ticket_number"] == premier_ticket.number`
    - Vérifier : `"TICKET_ALREADY_ACTIVE" == detail["code"]`
    - _Requirements: 3.4, 3.5_

- [ ]* 7. Écrire les tests de propriétés dans `tests/test_ticket_service_properties.py`
  - [ ]* 7.1 `test_any_active_status_blocks_creation` — Property 1
    - **Property 1 : Tout statut actif bloque la création**
    - **Validates: Requirements 1.2, 4.1, 4.3**
    - Utiliser `@given(st.sampled_from(ACTIVE_STATUSES))` avec `@settings(max_examples=100)`
    - Pour chaque statut : créer un ticket manuellement dans ce statut dans la DB, tenter
      de créer un second ticket pour le même `user_id`, vérifier HTTP 409
    - Tag : `Feature: sprint1-task03-one-active-ticket, Property 1: tout statut actif bloque`

  - [ ]* 7.2 `test_terminal_statuses_allow_creation` — Property 2
    - **Property 2 : Tout statut terminal libère la création**
    - **Validates: Requirements 1.3, 5.1, 5.2, 5.3**
    - Utiliser `@given(st.sampled_from([TicketStatus.DONE, TicketStatus.CANCELLED]))`
    - Pour chaque statut terminal : créer un ticket dans ce statut, créer un second ticket,
      vérifier que la création réussit sans 409
    - Tag : `Feature: sprint1-task03-one-active-ticket, Property 2: statut terminal libère`

  - [ ]* 7.3 `test_409_contains_redirect_fields` — Property 3
    - **Property 3 : La réponse 409 contient les champs de redirection mobile**
    - **Validates: Requirements 1.4, 3.1, 3.2, 3.3, 3.4, 3.5**
    - Utiliser `@given(st.sampled_from(ACTIVE_STATUSES))` avec `@settings(max_examples=100)`
    - Déclencher la 409 et vérifier la présence et la valeur exacte de `active_ticket_id`
      et `active_ticket_number` dans `exc_info.value.detail`
    - Tag : `Feature: sprint1-task03-one-active-ticket, Property 3: champs 409 présents`

  - [ ]* 7.4 `test_detection_ignores_agency_id` — Property 4
    - **Property 4 : Détection sans filtre agence**
    - **Validates: Requirements 1.1, 2.1, 2.2**
    - Créer un ticket dans l'agence A pour `user_id`
    - Appeler `_get_active_ticket(user_id)` directement
    - Vérifier que le ticket retourné n'est pas `None` — sans jamais passer `agency_id`
    - Répéter avec différentes agences générées aléatoirement
    - Tag : `Feature: sprint1-task03-one-active-ticket, Property 4: détection sans agency_id`

- [ ] 8. Vérifier la constante `ACTIVE_STATUSES`
  - Écrire `test_active_statuses_constant` dans `tests/test_ticket_service.py`
  - Assertion : `set(ACTIVE_STATUSES) == {TicketStatus.WAITING, TicketStatus.CALLED, TicketStatus.SERVING, TicketStatus.ABSENT, TicketStatus.TRANSFERRED, TicketStatus.INCOMPLETE}`
  - _Requirements: 1.5_

- [ ] 9. Checkpoint final — tous les tests doivent passer
  - Ensure all tests pass, ask the user if questions arise.
  - Vérifier que `test_create_ticket_duplicate_raises_409` (test modifié) passe
  - Vérifier que tous les nouveaux tests passent
  - Commande : `pytest tests/test_ticket_service.py -v`

## Notes

- Les tâches 7.x sont optionnelles (marquées `*`) et peuvent être sautées pour un MVP rapide
- Les tests unitaires (tâches 6.x) sont obligatoires et suffisants pour la PR
- La constante `ACTIVE_STATUSES` doit être placée **au niveau module** (pas dans la classe)
  pour permettre son import direct dans les tests de propriétés
- Pas de migration Alembic, pas de changement de schéma Pydantic, pas de changement de routeur
- Avant de commencer : `git checkout main && git pull && git checkout -b fix/one-active-ticket-global`
