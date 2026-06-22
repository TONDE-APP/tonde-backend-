# Requirements Document — TASK-05 : Redis Pub/Sub activé

## Introduction

L'architecture temps réel de TONDE repose sur Redis Pub/Sub pour propager les événements WebSocket entre instances. Dans l'état actuel, le `QueueWebSocketManager` expose une méthode `start_redis_listener()` dans `app/websocket/queue_ws.py`, mais cette méthode n'est jamais démarrée dans le lifespan de `app/main.py`. En conséquence, les événements publiés par le Queue Engine (appel de ticket, mise à jour de position, broadcast) ne parviennent jamais aux clients WebSocket connectés.

Cette feature applique la **DÉCISION 5** validée par Vital : réécrire `start_redis_listener()` pour utiliser `psubscribe("tonde:events:*")` (capture toutes les organisations), ajouter une boucle de reconnexion automatique avec backoff de 5 secondes, et démarrer le listener comme tâche asyncio non-bloquante dans `lifespan()`.

## Glossaire

- **WS_Manager** : instance globale `ws_manager` de `QueueWebSocketManager` dans `app/websocket/queue_ws.py`, qui gère toutes les connexions WebSocket actives.
- **Redis_Listener** : tâche asyncio de fond lancée par `ws_manager.start_redis_listener()`, qui consomme le canal Pub/Sub Redis et dispatche les événements aux clients connectés.
- **Pub/Sub_Channel** : canal Redis nommé `tonde:events:{org_id}` sur lequel le Queue Engine publie les événements. Le pattern `tonde:events:*` capture tous les canaux de toutes les organisations.
- **Dispatch** : opération interne `_dispatch_event(event)` qui route un événement vers le bon client WebSocket en fonction de son `type` (envoi ciblé par `ticket_id` ou broadcast par `agency_id`).
- **Lifespan** : gestionnaire de contexte asyncio de FastAPI dans `app/main.py` qui exécute le code de démarrage et d'arrêt de l'application.
- **psubscribe** : commande Redis qui souscrit à un pattern de canaux (wildcard `*`), à la différence de `subscribe` qui cible un canal unique.
- **pmessage** : type de message Redis retourné par un abonnement pattern (`psubscribe`), à distinguer du type `message` retourné par `subscribe`.
- **Backoff** : délai d'attente fixe (5 secondes) avant toute tentative de reconnexion après une erreur Redis, pour éviter les reconnexions en boucle rapide.
- **asyncio.create_task** : fonction Python standard pour démarrer une coroutine comme tâche de fond non-bloquante dans la boucle d'événements asyncio.

---

## Requirements

### Requirement 1 : Réécriture de `start_redis_listener()` avec `psubscribe`

**User Story :** En tant que système backend, je veux que le listener Redis écoute sur le pattern `tonde:events:*` plutôt que sur un seul canal, afin de recevoir les événements de toutes les organisations sans avoir à démarrer un listener par organisation.

#### Acceptance Criteria

1. THE WS_Manager SHALL expose `start_redis_listener()` as an async method with no parameters other than `self`.
2. WHEN `start_redis_listener()` is executing, THE Redis_Listener SHALL subscribe to the pattern `tonde:events:*` using `psubscribe`.
3. WHEN a message of type `pmessage` is received on the Pub/Sub channel, THE Redis_Listener SHALL deserialize its `data` field as JSON and pass the resulting dict to `_dispatch_event()`.
4. WHEN a message of type other than `message` or `pmessage` is received, THE Redis_Listener SHALL silently ignore it and continue listening.
5. THE Redis_Listener SHALL process each incoming message without blocking the asyncio event loop.

---

### Requirement 2 : Reconnexion automatique avec backoff

**User Story :** En tant qu'opérateur système, je veux que le listener Redis se reconnecte automatiquement après une erreur de connexion, afin que la diffusion WebSocket reprenne sans intervention manuelle lorsque Redis redevient disponible.

#### Acceptance Criteria

1. WHEN an exception occurs inside `start_redis_listener()`, THE Redis_Listener SHALL log the exception with level ERROR including the message "Redis Pub/Sub déconnecté" and the exception detail.
2. WHEN an exception occurs inside `start_redis_listener()`, THE Redis_Listener SHALL wait exactly 5 seconds before attempting to reconnect.
3. WHEN the reconnection attempt is made, THE Redis_Listener SHALL re-acquire a Redis connection via `get_redis()` and re-subscribe to `tonde:events:*`.
4. THE Redis_Listener SHALL continue reconnection attempts indefinitely until the application is stopped, without raising an unhandled exception to the caller.

---

### Requirement 3 : Démarrage non-bloquant dans le lifespan de `main.py`

**User Story :** En tant que développeur, je veux que le listener Redis soit démarré au lancement de l'API comme tâche de fond, afin que le démarrage de l'application ne soit pas bloqué et que le listener soit actif dès la première requête WebSocket.

#### Acceptance Criteria

1. WHEN the FastAPI application starts, THE Lifespan SHALL call `asyncio.create_task(ws_manager.start_redis_listener())` after the Redis connection is verified.
2. WHEN `asyncio.create_task()` is called with `start_redis_listener()`, THE application startup SHALL not block waiting for the listener to complete.
3. THE Lifespan SHALL log a confirmation message at level INFO after creating the listener task (e.g., "Redis Pub/Sub — Listener démarré en tâche de fond").
4. WHEN the FastAPI application starts, THE Lifespan SHALL import `asyncio` at the module level in `app/main.py`.

---

### Requirement 4 : Dispatch correct des événements aux clients WebSocket

**User Story :** En tant que client mobile TONDE, je veux recevoir les notifications temps réel (appel de mon numéro, mise à jour de position, broadcast d'agence) dès qu'elles sont publiées par le Queue Engine, même si je suis connecté à une instance différente du serveur.

#### Acceptance Criteria

1. WHEN a `your_turn` event is received by the Redis_Listener, THE WS_Manager SHALL call `send_to_ticket(event["ticket_id"], event)` to deliver it to the correct mobile client.
2. WHEN a `ticket_called` event is received by the Redis_Listener, THE WS_Manager SHALL call `broadcast_to_agency(event["agency_id"], event)` to deliver it to all clients in the waiting room.
3. WHEN a `queue_update` event is received by the Redis_Listener, THE WS_Manager SHALL call `send_to_ticket(event["ticket_id"], event)` to deliver it to the correct mobile client.
4. WHEN a `broadcast_message` event is received by the Redis_Listener, THE WS_Manager SHALL call `broadcast_to_agency(event["agency_id"], event)` to deliver it to all clients in the waiting room.
5. WHEN an event with an unknown `type` is received, THE WS_Manager SHALL log it at DEBUG level and not raise an exception.

---

### Requirement 5 : Robustesse face aux messages malformés

**User Story :** En tant qu'opérateur système, je veux que le listener Redis continue de fonctionner même si un message Redis est invalide ou malformé, afin qu'un seul message corrompu n'interrompe pas la diffusion de tous les événements suivants.

#### Acceptance Criteria

1. WHEN the `data` field of a Redis message cannot be deserialized as JSON, THE Redis_Listener SHALL log the error at ERROR level and continue listening for subsequent messages.
2. WHEN `_dispatch_event()` raises an exception for a given event, THE Redis_Listener SHALL log the error at ERROR level and continue listening for subsequent messages.
3. IF the Redis message `data` field is empty or `None`, THEN THE Redis_Listener SHALL skip the message and continue listening.
