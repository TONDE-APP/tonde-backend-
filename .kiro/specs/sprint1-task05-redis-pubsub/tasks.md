# Implementation Plan — TASK-05 : Redis Pub/Sub activé

## Overview

Deux fichiers à modifier, zéro nouveau fichier, zéro migration.
Ordre obligatoire : `queue_ws.py` en premier, puis `main.py`.

Branche Git : `feat/redis-pubsub-listener`

---

## Tasks

- [ ] 1. Réécrire `start_redis_listener()` dans `app/websocket/queue_ws.py`
  - [ ] 1.1 Supprimer le paramètre `org_id` de la signature
    - Nouvelle signature : `async def start_redis_listener(self) -> None:`
    - Mettre à jour la docstring pour décrire : boucle infinie, psubscribe, reconnexion 5s
    - _Requirements: 1.1_

  - [ ] 1.2 Remplacer le corps de la méthode par la version avec `while True`
    - Envelopper tout le corps dans `while True:`
    - Bloc `try` : `get_redis()` → `pubsub()` → `psubscribe("tonde:events:*")` → `async for message`
    - Bloc `except Exception as e` : `logger.error(...)` → `await asyncio.sleep(5)`
    - _Requirements: 1.2, 2.1, 2.2, 2.3, 2.4_

  - [ ] 1.3 Mettre à jour le filtre de type de message
    - Remplacer `if message["type"] != "message":` par `if message["type"] not in ("message", "pmessage"):`
    - Ajouter `data = message.get("data")` et `if not data: continue` avant la désérialisation JSON
    - _Requirements: 1.3, 1.4, 5.3_

  - [ ] 1.4 Isoler les erreurs de dispatch dans un try/except interne
    - Envelopper `json.loads(data)` et `await self._dispatch_event(event)` dans un bloc `try`
    - `except json.JSONDecodeError` → `logger.error(f"message JSON invalide: {e}")` → continuer
    - `except Exception as e` → `logger.error(f"erreur dispatch: {e}", exc_info=True)` → continuer
    - Ces exceptions internes NE doivent PAS remonter au `except` externe de reconnexion
    - _Requirements: 5.1, 5.2_

  - [ ] 1.5 Vérifier que `asyncio` est importé en tête du fichier
    - `import asyncio` est déjà présent dans `queue_ws.py` — confirmer qu'il n'est pas supprimé
    - _Requirements: 1.5_

- [ ] 2. Mettre à jour `app/main.py`
  - [ ] 2.1 Ajouter `import asyncio` en tête du fichier (imports module-level)
    - _Requirements: 3.4_

  - [ ] 2.2 Brancher le listener dans `lifespan()`
    - Localiser le bloc après `await redis.ping()` et `logger.info("Redis — Connexion établie")`
    - Ajouter immédiatement après :
      ```python
      asyncio.create_task(ws_manager.start_redis_listener())
      logger.info("Redis Pub/Sub — Listener démarré en tâche de fond")
      ```
    - _Requirements: 3.1, 3.2, 3.3_

- [ ] 3. Checkpoint — démarrage de l'app sans erreur
  - Lancer `docker-compose up` (ou `uvicorn app.main:app --reload`)
  - Vérifier dans les logs : `"Redis Pub/Sub — écoute active sur tonde:events:*"`
  - Vérifier que l'app démarre sans exception et répond sur `/health`

- [ ] 4. Écrire les tests dans `tests/test_queue_ws.py` (nouveau fichier)
  - [ ] 4.1 `test_listener_dispatches_your_turn_event`
    - Mock pubsub retournant 1 message `pmessage` avec `type: "your_turn"` et `ticket_id`
    - Vérifier que `ws_manager._dispatch_event` est appelé avec le bon dict
    - _Requirements: 4.1_

  - [ ] 4.2 `test_listener_dispatches_ticket_called_event`
    - Mock pubsub retournant 1 message `pmessage` avec `type: "ticket_called"` et `agency_id`
    - Vérifier que `broadcast_to_agency` est appelé avec le bon `agency_id`
    - _Requirements: 4.2_

  - [ ] 4.3 `test_listener_skips_subscribe_type_messages`
    - Mock pubsub retournant 1 message de type `"subscribe"` (confirmation de souscription Redis)
    - Vérifier que `_dispatch_event` n'est PAS appelé
    - _Requirements: 1.4_

  - [ ] 4.4 `test_listener_handles_invalid_json_gracefully`
    - Mock pubsub retournant 1 message avec `data: "not-valid-json"`
    - Vérifier qu'aucune exception n'est levée et que la boucle continue
    - _Requirements: 5.1_

  - [ ] 4.5 `test_listener_handles_dispatch_exception_gracefully`
    - Mock `_dispatch_event` qui lève `Exception("dispatch error")`
    - Vérifier qu'aucune exception ne remonte et que la boucle continue
    - _Requirements: 5.2_

  - [ ] 4.6 `test_listener_reconnects_after_redis_exception`
    - Mock `get_redis()` qui lève une exception au premier appel, puis réussit au second
    - Mock `asyncio.sleep` pour éviter d'attendre 5s en test
    - Vérifier que `get_redis()` est appelé une deuxième fois (reconnexion)
    - _Requirements: 2.2, 2.3_

- [ ] 5. Checkpoint final — tous les tests au vert
  - Lancer `pytest tests/ -v --tb=short`
  - Vérifier que les tests existants ne sont pas cassés
  - Vérifier que les 6 nouveaux tests passent

## Notes

- `_dispatch_event()` n'est PAS modifié — elle est déjà correcte
- `publish_event()` n'est PAS modifié — elle publie déjà sur `tonde:events:{org_id}`
- La compatibilité du canal est garantie : `publish("tonde:events:org-123")` est capturé par `psubscribe("tonde:events:*")`
- Avant de commencer : `git checkout main && git pull && git checkout -b feat/redis-pubsub-listener`
- Pour contrôler la boucle infinie dans les tests, utiliser `asyncio.create_task()` + `task.cancel()` après un court `asyncio.sleep(0.1)`
