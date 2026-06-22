# Requirements Document

## Introduction

TASK-02 introduit la persistance des refresh tokens en base de données PostgreSQL afin de permettre la révocation de session, le support multi-device et un logout sécurisé. Actuellement, le refresh token est entièrement stateless : une fois émis, il ne peut pas être invalidé avant son expiration naturelle (7 jours). Cette absence de mécanisme de révocation constitue un risque de sécurité critique — un token volé reste exploitable pendant toute sa durée de vie.

La solution consiste à créer une table `refresh_tokens`, à stocker le `sha256(token)` lors de chaque émission, et à ajouter la logique de révocation/rotation dans `AuthService`. Deux nouveaux endpoints sont créés : `POST /auth/logout` et `POST /auth/logout/all`.

## Glossaire

- **AuthService** : Service d'authentification — `app/services/auth_service.py`
- **RefreshToken** : Modèle SQLAlchemy représentant une ligne de la table `refresh_tokens`
- **token_hash** : Empreinte SHA-256 du JWT refresh token brut — la seule forme stockée en base
- **rotation** : Mécanisme par lequel chaque appel à `POST /auth/refresh` révoque l'ancien token et émet un nouveau
- **révocation** : Mise à jour de `revoked_at = now()` sur une ou plusieurs lignes `refresh_tokens`
- **device_id** : Identifiant opaque fourni par le client pour distinguer les sessions par appareil
- **session** : Paire (user_id, refresh_token actif) représentant une connexion active d'un device

---

## Requirements

### Requirement 1 — Modèle et migration

**User Story :** En tant que développeur backend, je veux une table `refresh_tokens` en base de données, afin de pouvoir persister, consulter et révoquer les sessions utilisateurs.

#### Acceptance Criteria

1. THE AuthService SHALL créer un enregistrement dans `refresh_tokens` à chaque émission d'un refresh token JWT.
2. THE RefreshToken model SHALL stocker `sha256(token_jwt_brut)` dans le champ `token_hash` — jamais le token en clair.
3. THE RefreshToken model SHALL inclure les champs : `id` (UUID PK), `user_id` (FK → `users.id` CASCADE DELETE), `token_hash` (SHA-256, unique), `device_id` (nullable), `ip_address` (nullable), `expires_at` (datetime), `revoked_at` (datetime nullable), `created_at` (datetime).
4. WHEN un utilisateur est supprimé, THE système SHALL supprimer en cascade tous ses enregistrements `refresh_tokens` via la contrainte FK `ON DELETE CASCADE`.
5. THE Migration Alembic SHALL créer la table `refresh_tokens` avec tous les champs et index définis.

---

### Requirement 2 — Persistance lors de l'émission d'un token

**User Story :** En tant que système, je veux persister chaque refresh token émis, afin de pouvoir le valider et le révoquer ultérieurement.

#### Acceptance Criteria

1. WHEN un utilisateur se connecte via `verify_otp`, `register_email` ou `login_email`, THE AuthService SHALL persister le nouveau refresh token dans la table `refresh_tokens` avant de retourner la réponse.
2. WHEN le client fournit un `device_id` dans la requête, THE AuthService SHALL l'associer à l'enregistrement `refresh_tokens` correspondant.
3. THE AuthService SHALL extraire `expires_at` depuis le payload JWT du refresh token et le stocker en base de données.
4. IF la persistance en base échoue, THEN THE AuthService SHALL lever une `HTTPException` 500 et ne pas retourner de token au client.

---

### Requirement 3 — Validation lors du refresh

**User Story :** En tant que client mobile, je veux renouveler mon access token avec mon refresh token, afin de rester connecté sans ressaisir mes identifiants.

#### Acceptance Criteria

1. WHEN un client envoie un refresh token valide à `POST /auth/refresh`, THE AuthService SHALL vérifier la signature JWT ET la présence d'une ligne active (non révoquée, non expirée) en base de données.
2. IF le token JWT est valide mais absent de la table `refresh_tokens`, THEN THE AuthService SHALL retourner HTTP 401 avec le code `INVALID_REFRESH_TOKEN`.
3. IF le token JWT est valide mais que `revoked_at` est non-NULL, THEN THE AuthService SHALL retourner HTTP 401 avec le code `TOKEN_REVOKED`.
4. IF le token est valide et actif, THEN THE AuthService SHALL effectuer la rotation : révoquer l'ancien token, créer un nouveau refresh token, persister le nouveau, et retourner le nouvel `access_token` et le nouveau `refresh_token`.
5. THE AuthService SHALL retourner le nouveau `refresh_token` dans la réponse de `POST /auth/refresh`.

---

### Requirement 4 — Endpoint logout (révocation d'une session)

**User Story :** En tant qu'utilisateur, je veux me déconnecter d'un appareil spécifique, afin de sécuriser mon compte en cas de perte ou vol de device.

#### Acceptance Criteria

1. WHEN un client envoie `POST /auth/logout` avec un `refresh_token` valide dans le body, THE AuthService SHALL mettre à jour `revoked_at = now()` sur l'enregistrement correspondant.
2. IF le `refresh_token` fourni est introuvable en base, THEN THE AuthService SHALL retourner HTTP 401 avec le code `INVALID_REFRESH_TOKEN`.
3. IF le `refresh_token` est déjà révoqué, THEN THE AuthService SHALL retourner HTTP 400 avec le code `TOKEN_ALREADY_REVOKED`.
4. WHEN la révocation réussit, THE AuthService SHALL retourner HTTP 200 avec `{"success": true, "message": "Déconnecté avec succès"}`.
5. THE Router SHALL exposer cet endpoint sans dépendance `get_current_user` — le refresh token suffit à identifier la session à révoquer.

---

### Requirement 5 — Endpoint logout/all (révocation de toutes les sessions)

**User Story :** En tant qu'utilisateur, je veux me déconnecter de tous mes appareils en une seule action, afin de sécuriser mon compte après une compromission.

#### Acceptance Criteria

1. WHEN un client authentifié envoie `POST /auth/logout/all`, THE AuthService SHALL révoquer tous les refresh tokens actifs de l'utilisateur en mettant `revoked_at = now()`.
2. WHILE un utilisateur possède plusieurs sessions actives, THE AuthService SHALL toutes les révoquer en une seule requête base de données (`UPDATE ... WHERE user_id = ? AND revoked_at IS NULL`).
3. WHEN la révocation réussit, THE AuthService SHALL retourner HTTP 200 avec `{"success": true, "message": "Toutes les sessions révoquées", "sessions_revoked": N}` où N est le nombre de tokens révoqués.
4. THE Router SHALL protéger cet endpoint avec `Depends(get_current_user)` — un access token valide est requis.

---

### Requirement 6 — Support multi-device

**User Story :** En tant qu'utilisateur, je veux utiliser TONDE depuis plusieurs appareils simultanément, afin de ne pas être déconnecté d'un device quand j'utilise un autre.

#### Acceptance Criteria

1. THE AuthService SHALL permettre plusieurs enregistrements `refresh_tokens` actifs pour le même `user_id` (une ligne par device).
2. WHEN un `device_id` est fourni et qu'une session active existe déjà pour ce `device_id`, THE AuthService SHALL révoquer l'ancienne session du device avant d'en créer une nouvelle.
3. THE Logout endpoint SHALL ne révoquer que le token fourni dans le body, sans affecter les autres sessions du même utilisateur.

---

### Requirement 7 — Schémas Pydantic

**User Story :** En tant que développeur, je veux des schémas Pydantic v2 clairs pour les nouveaux endpoints et le `device_id` optionnel, afin de maintenir la cohérence de l'API.

#### Acceptance Criteria

1. THE système SHALL ajouter `device_id: str | None = None` dans les schémas de requête `VerifyOtpRequest`, `RegisterEmailRequest`, et `LoginEmailRequest` sans rendre ce champ obligatoire.
2. THE système SHALL ajouter `device_id: str | None = None` dans `AuthResponse` pour que le client sache quel device_id a été enregistré pour sa session.
3. THE système SHALL créer un schéma `LogoutRequest` avec un champ `refresh_token: str` obligatoire.
4. THE système SHALL créer un schéma `RefreshResponse` contenant `access_token`, `refresh_token`, et `token_type` pour remplacer le `dict` actuellement retourné par `refresh_token()`.

---

### Requirement 8 — Sécurité du stockage

**User Story :** En tant qu'architecte sécurité, je veux que les refresh tokens ne soient jamais stockés en clair, afin de limiter l'impact d'une fuite de base de données.

#### Acceptance Criteria

1. THE AuthService SHALL toujours appliquer `hashlib.sha256(token.encode()).hexdigest()` avant toute opération d'écriture ou de lecture en base impliquant un token.
2. THE colonne `token_hash` SHALL avoir une contrainte `UNIQUE` en base de données.
3. IF un attaquant obtient l'accès en lecture à la table `refresh_tokens`, THE système SHALL ne pas lui permettre de reconstituir les tokens JWT originaux à partir des hash stockés.
4. THE AuthService SHALL utiliser une recherche par hash lors de la validation (`SELECT ... WHERE token_hash = sha256(token_reçu)`) — jamais en clair.
