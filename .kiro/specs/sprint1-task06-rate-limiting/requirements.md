# Requirements Document

## Introduction

TASK-06 consiste à brancher `slowapi==0.1.9` (déjà présent dans `requirements.txt` mais non configuré) sur l'API TONDE afin de protéger les endpoints d'authentification critiques et les connexions WebSocket contre les attaques par force brute, le flood SMS et l'abus de rotation de tokens. La limite est appliquée par adresse IP. En cas de dépassement, le système retourne HTTP 429 avec un header `Retry-After`.

## Glossaire

- **Rate_Limiter** : instance `slowapi.Limiter` configurée avec `get_remote_address` comme clé de partitionnement par IP.
- **Middleware_Setup** : fonction `setup_rate_limiting()` dans `app/core/middlewares.py` qui attache le `Rate_Limiter` à l'application FastAPI.
- **Auth_Router** : module `app/routers/auth.py` exposant les endpoints d'authentification.
- **Tickets_Router** : module `app/routers/tickets.py` exposant les endpoints REST et WebSocket de gestion des tickets.
- **IP_Address** : adresse IPv4 ou IPv6 de l'appelant, extraite par `slowapi.util.get_remote_address`.
- **Window** : fenêtre glissante d'une minute utilisée pour le comptage des requêtes.
- **Retry-After** : header HTTP standard indiquant le délai en secondes avant qu'une nouvelle requête soit acceptée.

---

## Requirements

### Requirement 1 — Configuration du Rate Limiter

**User Story :** En tant que Tech Lead, je veux un module central de configuration du rate limiting, afin que l'activation et la maintenance soient isolées du reste de l'application.

#### Acceptance Criteria

1. THE `Rate_Limiter` SHALL être instancié dans `app/core/middlewares.py` avec `key_func=get_remote_address`.
2. THE `Middleware_Setup` SHALL attacher le `Rate_Limiter` à `app.state.limiter` de l'instance FastAPI reçue en paramètre.
3. THE `Middleware_Setup` SHALL enregistrer `_rate_limit_exceeded_handler` comme handler de l'exception `RateLimitExceeded` sur l'instance FastAPI.
4. WHEN `setup_rate_limiting(app)` est appelée dans `app/main.py`, THE `Rate_Limiter` SHALL être actif pour toutes les requêtes entrantes.
5. IF `setup_rate_limiting` n'est pas appelée au démarrage, THEN THE `Rate_Limiter` SHALL ne pas intercepter les requêtes (activation explicite requise).

---

### Requirement 2 — Protection de `POST /auth/login`

**User Story :** En tant qu'administrateur de sécurité, je veux limiter les tentatives de login par email, afin d'empêcher les attaques brute force sur les mots de passe.

#### Acceptance Criteria

1. THE `Auth_Router` SHALL appliquer une limite de 10 requêtes par minute par `IP_Address` sur l'endpoint `POST /auth/login`.
2. WHEN une `IP_Address` atteint 10 requêtes dans la `Window`, THE `Rate_Limiter` SHALL retourner HTTP 429 pour toute requête supplémentaire dans la même `Window`.
3. WHEN HTTP 429 est retourné, THE `Rate_Limiter` SHALL inclure le header `Retry-After` indiquant le nombre de secondes avant la prochaine `Window`.
4. WHEN le compteur d'une `IP_Address` est en dessous du seuil, THE `Auth_Router` SHALL traiter la requête normalement.

---

### Requirement 3 — Protection de `POST /auth/register/phone`

**User Story :** En tant qu'administrateur de sécurité, je veux limiter les inscriptions par téléphone, afin d'éviter le flood de SMS vers Africa's Talking et les frais associés.

#### Acceptance Criteria

1. THE `Auth_Router` SHALL appliquer une limite de 5 requêtes par minute par `IP_Address` sur l'endpoint `POST /auth/register/phone`.
2. WHEN une `IP_Address` dépasse 5 requêtes dans la `Window`, THE `Rate_Limiter` SHALL retourner HTTP 429.
3. WHEN HTTP 429 est retourné, THE `Rate_Limiter` SHALL inclure le header `Retry-After`.

---

### Requirement 4 — Protection de `POST /auth/verify-otp`

**User Story :** En tant qu'administrateur de sécurité, je veux limiter les tentatives de vérification OTP, afin d'empêcher le brute force des codes à 6 chiffres.

#### Acceptance Criteria

1. THE `Auth_Router` SHALL appliquer une limite de 5 requêtes par minute par `IP_Address` sur l'endpoint `POST /auth/verify-otp`.
2. WHEN une `IP_Address` dépasse 5 requêtes dans la `Window`, THE `Rate_Limiter` SHALL retourner HTTP 429.
3. WHEN HTTP 429 est retourné, THE `Rate_Limiter` SHALL inclure le header `Retry-After`.

---

### Requirement 5 — Protection de `POST /auth/refresh`

**User Story :** En tant qu'administrateur de sécurité, je veux limiter les appels de rotation de token, afin d'empêcher l'abus du mécanisme de refresh.

#### Acceptance Criteria

1. THE `Auth_Router` SHALL appliquer une limite de 20 requêtes par minute par `IP_Address` sur l'endpoint `POST /auth/refresh`.
2. WHEN une `IP_Address` dépasse 20 requêtes dans la `Window`, THE `Rate_Limiter` SHALL retourner HTTP 429.
3. WHEN HTTP 429 est retourné, THE `Rate_Limiter` SHALL inclure le header `Retry-After`.

---

### Requirement 6 — Protection des connexions WebSocket

**User Story :** En tant qu'administrateur de sécurité, je veux limiter les connexions WebSocket par IP, afin d'empêcher le flood de connexions qui épuiserait les ressources serveur.

#### Acceptance Criteria

1. THE `Tickets_Router` SHALL appliquer une limite de 10 connexions par minute par `IP_Address` sur l'endpoint WebSocket `GET /ws/queue/{ticket_id}`.
2. THE `Tickets_Router` SHALL appliquer une limite de 10 connexions par minute par `IP_Address` sur l'endpoint WebSocket `GET /ws/counter/{counter_id}`.
3. WHEN une `IP_Address` dépasse 10 connexions WebSocket dans la `Window`, THE `Rate_Limiter` SHALL retourner HTTP 429 avant l'établissement de la connexion.
4. WHEN HTTP 429 est retourné, THE `Rate_Limiter` SHALL inclure le header `Retry-After`.

---

### Requirement 7 — Signature des endpoints protégés

**User Story :** En tant que développeur backend, je veux que chaque endpoint protégé accepte `request: Request` comme premier paramètre, afin de satisfaire le contrat d'interface requis par `slowapi`.

#### Acceptance Criteria

1. THE `Auth_Router` SHALL déclarer `request: Request` comme premier paramètre dans chaque fonction handler décorée avec `@limiter.limit(...)`.
2. THE `Tickets_Router` SHALL déclarer `websocket: WebSocket` comme premier paramètre dans chaque fonction handler WebSocket décorée avec `@limiter.limit(...)` (slowapi accepte WebSocket en lieu de Request pour les endpoints WebSocket).
3. IF `request: Request` est absent d'un handler décoré, THEN THE `Rate_Limiter` SHALL lever une erreur de configuration au démarrage de l'application.

---

### Requirement 8 — Comportement HTTP 429 standard

**User Story :** En tant que développeur mobile Flutter, je veux recevoir une réponse structurée et des headers clairs en cas de dépassement de limite, afin de pouvoir implémenter un backoff côté client.

#### Acceptance Criteria

1. WHEN le `Rate_Limiter` bloque une requête, THE API SHALL retourner HTTP 429 avec un body JSON contenant un message d'erreur lisible.
2. WHEN HTTP 429 est retourné, THE API SHALL inclure le header `Retry-After` avec la valeur en secondes jusqu'à la prochaine `Window`.
3. THE `Rate_Limiter` SHALL ne pas retourner HTTP 500 ou HTTP 503 en cas de dépassement de limite.

---

### Requirement 9 — Aucune nouvelle dépendance

**User Story :** En tant que Tech Lead, je veux que cette feature n'introduise aucun nouveau package, afin de garder le périmètre de dépendances sous contrôle.

#### Acceptance Criteria

1. THE implémentation SHALL utiliser uniquement `slowapi==0.1.9` déjà présent dans `requirements.txt`.
2. THE `requirements.txt` SHALL ne pas être modifié par cette tâche.
3. IF une dépendance transitive manque, THEN THE développeur SHALL signaler le blocage à Vital avant toute modification.
