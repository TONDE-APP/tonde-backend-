# Requirements Document

## Introduction

TASK-01 corrige une faille de sécurité critique : l'OTP (One-Time Password) envoyé par SMS est actuellement stocké en clair dans Redis. Si Redis est compromis, tous les OTP actifs sont exposés et n'importe quel attaquant peut se connecter au compte de n'importe quel utilisateur.

La correction consiste à ne stocker que le hash SHA-256 de l'OTP dans Redis. La vérification compare alors le hash du code saisi par l'utilisateur avec le hash stocké. L'OTP en clair ne transite plus jamais par la persistance.

Le contrat API (endpoints, schémas de requête/réponse) reste strictement identique. Seule la couche de persistance Redis et la logique de vérification changent.

## Glossaire

- **OTP** : One-Time Password — code numérique à 6 chiffres à durée de vie limitée, envoyé par SMS pour authentifier un utilisateur lors d'une connexion par téléphone.
- **DEV_OTP** : Code OTP fixe `123456` utilisé uniquement en `ENVIRONMENT=development` pour faciliter les tests sans envoi de SMS réel.
- **Hash SHA-256** : Empreinte hexadécimale de 64 caractères produite par l'algorithme SHA-256, non réversible. Utilisé ici pour éviter de persister l'OTP en clair.
- **OTP_Hasher** : Fonction pure `_hash_otp(otp: str) -> str` qui applique `hashlib.sha256(otp.encode()).hexdigest()`.
- **Redis_OTP_Store** : Couche Redis responsable de la persistance des OTP — fonctions `save_otp()` et `get_otp()` dans `app/core/redis.py`.
- **AuthService** : Service applicatif `app/services/auth_service.py` responsable du flux d'authentification OTP complet.
- **TTL** : Time To Live — durée de validité d'une clé Redis, configurée via `settings.OTP_EXPIRE_MINUTES * 60` secondes.

---

## Requirements

### Requirement 1 — Hashage de l'OTP avant persistance

**User Story :** En tant que responsable sécurité, je veux que l'OTP ne soit jamais stocké en clair dans Redis, afin qu'une compromission de Redis n'expose pas les codes actifs des utilisateurs.

#### Acceptance Criteria

1. WHEN `save_otp(phone, otp)` est appelé, THE `Redis_OTP_Store` SHALL stocker `hashlib.sha256(otp.encode()).hexdigest()` à la clé `tonde:otp:{phone}`, et non la valeur brute de `otp`.
2. WHEN `save_otp(phone, otp)` est appelé, THE `Redis_OTP_Store` SHALL appliquer un TTL égal à `settings.OTP_EXPIRE_MINUTES * 60` secondes sur la clé `tonde:otp:{phone}`.
3. WHEN `save_otp(phone, otp)` est appelé, THE `Redis_OTP_Store` SHALL réinitialiser le compteur de tentatives `tonde:otp_attempts:{phone}` à `"0"` avec le même TTL.
4. THE `OTP_Hasher` SHALL produire une chaîne hexadécimale de exactement 64 caractères pour tout OTP en entrée.
5. THE `OTP_Hasher` SHALL produire une valeur déterministe : deux appels avec le même `otp` produisent toujours le même hash.

---

### Requirement 2 — Vérification par comparaison de hash

**User Story :** En tant qu'utilisateur, je veux pouvoir saisir mon OTP et être authentifié correctement, afin d'accéder à TONDE sans que ma sécurité ne soit compromise.

#### Acceptance Criteria

1. WHEN `verify_otp(phone, otp_saisi)` est appelé et que le hash stocké dans Redis correspond à `hashlib.sha256(otp_saisi.encode()).hexdigest()`, THE `AuthService` SHALL considérer l'OTP comme valide et retourner les tokens JWT.
2. WHEN `verify_otp(phone, otp_saisi)` est appelé et que le hash stocké dans Redis ne correspond pas à `hashlib.sha256(otp_saisi.encode()).hexdigest()`, THE `AuthService` SHALL lever une `HTTPException` avec `status_code=400` et `code="INVALID_OTP"`.
3. WHEN `verify_otp(phone, otp_saisi)` est appelé et qu'aucune clé `tonde:otp:{phone}` n'existe dans Redis, THE `AuthService` SHALL lever une `HTTPException` avec `status_code=400` et `code="OTP_EXPIRED"`.
4. WHEN le nombre de tentatives dépasse `settings.OTP_MAX_ATTEMPTS`, THE `AuthService` SHALL lever une `HTTPException` avec `status_code=429` et `code="TOO_MANY_ATTEMPTS"`.
5. WHEN l'OTP est vérifié avec succès, THE `AuthService` SHALL supprimer les clés `tonde:otp:{phone}` et `tonde:otp_attempts:{phone}` de Redis.

---

### Requirement 3 — Compatibilité du mode développement

**User Story :** En tant que développeur, je veux que le DEV_OTP `123456` continue de fonctionner en `ENVIRONMENT=development`, afin de pouvoir tester le flux d'authentification sans avoir à dériver un hash manuellement.

#### Acceptance Criteria

1. WHILE `settings.ENVIRONMENT == "development"`, WHEN `register_phone(phone)` est appelé, THE `AuthService` SHALL utiliser `DEV_OTP = "123456"` comme valeur d'OTP.
2. WHILE `settings.ENVIRONMENT == "development"`, WHEN `register_phone(phone)` est appelé, THE `Redis_OTP_Store` SHALL stocker `hashlib.sha256("123456".encode()).hexdigest()` — soit le hash du DEV_OTP, pas le clair.
3. WHILE `settings.ENVIRONMENT == "development"`, WHEN `verify_otp(phone, "123456")` est appelé avec le compteur sous le seuil, THE `AuthService` SHALL authentifier l'utilisateur avec succès.
4. WHILE `settings.ENVIRONMENT == "development"`, WHEN `register_phone(phone)` retourne sa réponse, THE `AuthService` SHALL inclure `dev_otp: "123456"` dans la réponse (le clair, pour les tests), et non le hash.

---

### Requirement 4 — Contrat API inchangé

**User Story :** En tant que développeur mobile, je veux que les endpoints d'authentification aient exactement le même contrat qu'avant, afin de ne pas avoir à modifier l'application Flutter.

#### Acceptance Criteria

1. THE `AuthService` SHALL exposer `register_phone(phone)` avec le même schéma de réponse qu'avant la modification (champs `success`, `message`, `otp_sent`, `expires_in_seconds`, et `dev_otp` en développement).
2. THE `AuthService` SHALL exposer `verify_otp(phone, otp)` avec le même schéma de requête et le même schéma `AuthResponse` (champs `access_token`, `refresh_token`, `user`) qu'avant la modification.
3. IF une erreur se produit lors de la vérification, THEN THE `AuthService` SHALL retourner une `HTTPException` avec le même format structuré `{"code": "...", "message": "..."}` qu'avant la modification.

---

### Requirement 5 — Couverture de tests

**User Story :** En tant que Tech Lead, je veux que des tests vérifient explicitement le comportement du hashage, afin de garantir en CI que l'OTP en clair n'est jamais persisté.

#### Acceptance Criteria

1. THE test suite SHALL inclure un test `test_otp_stored_as_hash_not_plaintext` qui vérifie que la valeur passée à `r.setex` est une chaîne hexadécimale de 64 caractères et non la valeur brute de l'OTP.
2. THE test suite SHALL inclure un test `test_verify_otp_with_correct_hash_succeeds` qui mock `get_otp` pour retourner le hash SHA-256 du DEV_OTP et vérifie que `verify_otp` retourne un `AuthResponse` valide.
3. THE test suite SHALL inclure un test `test_verify_otp_with_wrong_code_fails` qui mock `get_otp` pour retourner le hash d'un OTP quelconque et vérifie que `verify_otp` avec un code différent lève `HTTPException(400, code="INVALID_OTP")`.
4. THE test suite SHALL inclure un test `test_dev_otp_123456_still_works` qui vérifie le flux complet `register_phone → verify_otp("123456")` en environnement développement.
5. WHEN les tests existants dans `tests/test_auth_service.py` mockent `get_otp`, THE test suite SHALL retourner le hash SHA-256 de la valeur attendue, pas la valeur en clair.
