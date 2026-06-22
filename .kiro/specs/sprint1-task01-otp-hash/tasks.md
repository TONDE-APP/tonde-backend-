# Implementation Plan : TASK-01 — Sécurité OTP SHA-256

## Overview

Trois fichiers à modifier, un fichier de test à créer. Les changements sont chirurgicaux : deux fonctions dans `redis.py`, une comparaison dans `auth_service.py`, et les mocks dans les tests existants. Aucune migration, aucun nouveau modèle.

Branche Git : `fix/otp-hash-redis`

## Tasks

- [ ] 1. Ajouter `_hash_otp()` et mettre à jour `save_otp()` dans `app/core/redis.py`
  - Ajouter `import hashlib` en tête de fichier (stdlib, pas de nouvelle dépendance)
  - Ajouter la fonction privée `_hash_otp(otp: str) -> str` avec docstring complète
  - Dans `save_otp()`, remplacer `otp` par `_hash_otp(otp)` dans l'appel `r.setex()`
  - Mettre à jour la docstring de `get_otp()` pour préciser qu'elle retourne un hash SHA-256
  - Ne pas modifier la signature de `save_otp()`, `get_otp()` ni aucune autre fonction Redis
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 2. Mettre à jour `verify_otp()` dans `app/services/auth_service.py`
  - Ajouter `_hash_otp` dans l'import depuis `app.core.redis`
  - Renommer la variable locale `stored_otp` en `stored_hash` pour clarté
  - Remplacer `if otp != stored_otp:` par `if _hash_otp(otp) != stored_hash:`
  - Mettre à jour la docstring de `verify_otp()` pour mentionner la comparaison de hash
  - Aucun autre changement dans la méthode (flux, ordre des vérifications, réponses identiques)
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 3. Mettre à jour les mocks dans `tests/test_auth_service.py`
  - Ajouter `import hashlib` en tête du fichier de test
  - Ajouter la constante `DEV_OTP_HASH = hashlib.sha256(DEV_OTP.encode()).hexdigest()` après l'import de `DEV_OTP`
  - Dans `test_verify_otp_creates_user_and_returns_jwt` : changer `return_value=DEV_OTP` → `return_value=DEV_OTP_HASH`
  - Dans `test_verify_otp_invalid_raises_400` : changer `return_value="654321"` → `return_value=hashlib.sha256("654321".encode()).hexdigest()`
  - Dans `test_verify_otp_too_many_attempts_raises_429` : changer `return_value="123456"` → `return_value=DEV_OTP_HASH`
  - Vérifier que `test_verify_otp_expired_raises_400` reste inchangé (`return_value=None` est toujours valide)
  - _Requirements: 5.5_

- [ ] 4. Checkpoint — tests existants au vert
  - Lancer `pytest tests/test_auth_service.py -v` et vérifier que tous les tests passent sans modification de comportement
  - Si un test échoue, revoir les étapes 1–3 avant de continuer
  - Assurer que les tests `test_register_phone_*`, `test_register_email_*`, `test_login_email_*`, `test_refresh_token_*` sont inchangés

- [ ] 5. Écrire les nouveaux tests unitaires dans `tests/test_auth_service.py`
  - [ ] 5.1 Ajouter `test_otp_stored_as_hash_not_plaintext`
    - Mocker `app.core.redis.get_redis` pour capturer les appels à `setex`
    - Appeler `save_otp("+25779000000", DEV_OTP)`
    - Vérifier que la valeur passée au 3ème argument de `setex` est `DEV_OTP_HASH` (64 chars hex) et non `DEV_OTP`
    - _Requirements: 1.1_

  - [ ] 5.2 Ajouter `test_verify_otp_with_correct_hash_succeeds`
    - Mock `get_otp` → `DEV_OTP_HASH`, `increment_otp_attempts` → 1, `delete_otp` → None
    - Appeler `verify_otp(VerifyOtpRequest(phone="+25779000001", otp=DEV_OTP))`
    - Vérifier que le résultat est un `AuthResponse` avec `access_token` non vide
    - _Requirements: 2.1_

  - [ ] 5.3 Ajouter `test_verify_otp_with_wrong_code_fails`
    - Mock `get_otp` → `hashlib.sha256("654321".encode()).hexdigest()`, `increment_otp_attempts` → 1
    - Appeler `verify_otp(VerifyOtpRequest(phone="+25779000002", otp="000000"))`
    - Vérifier `HTTPException(400)` avec `code="INVALID_OTP"`
    - _Requirements: 2.2_

  - [ ] 5.4 Ajouter `test_dev_otp_123456_still_works`
    - Patcher `save_otp` et `_send_otp_sms` pour éviter les appels Redis/SMS
    - Appeler `register_phone(RegisterPhoneRequest(phone="+25779000003"))` et vérifier `dev_otp="123456"` dans la réponse
    - Mocker `get_otp` → `DEV_OTP_HASH` pour la vérification
    - Appeler `verify_otp(VerifyOtpRequest(phone="+25779000003", otp="123456"))` et vérifier le succès
    - _Requirements: 3.1, 3.3, 3.4_

- [ ] 6. Écrire les tests par propriétés dans `tests/test_otp_hash_properties.py` (nouveau fichier)
  - Créer le fichier avec les imports : `pytest`, `hypothesis` (`given`, `settings`, `assume`, `strategies as st`), `hashlib`, `re`, `unittest.mock`, `AsyncMock`
  - Importer `_hash_otp`, `save_otp` depuis `app.core.redis`
  - Importer `AuthService`, `VerifyOtpRequest` depuis les modules appropriés
  - [ ]* 6.1 Écrire le test `test_hash_otp_produces_64_char_hex_deterministically`
    - **Property 1 : OTP_Hasher — format et déterminisme**
    - **Validates: Requirements 1.4, 1.5**
    - Stratégie : `st.text(alphabet="0123456789", min_size=4, max_size=8)`, 100 exemples
    - Assertions : `len(h) == 64`, match regex `[0-9a-f]{64}`, appel deux fois → même résultat

  - [ ]* 6.2 Écrire le test `test_save_otp_stores_hash_not_plaintext`
    - **Property 2 : save_otp ne stocke jamais le clair**
    - **Validates: Requirements 1.1**
    - Stratégie : `st.text(alphabet="0123456789", min_size=6, max_size=6)`, 100 exemples
    - Mock `get_redis`, capturer les arguments de `setex`, vérifier `stored == sha256(otp)` et `stored != otp`

  - [ ]* 6.3 Écrire le test `test_verify_otp_succeeds_for_any_correct_otp`
    - **Property 3 : vérification réussie pour tout OTP correct**
    - **Validates: Requirements 2.1**
    - Stratégie : `st.text(alphabet="0123456789", min_size=6, max_size=6)`, 100 exemples
    - Mock `get_otp` → `sha256(otp)`, vérifier `AuthResponse` avec tokens non vides

  - [ ]* 6.4 Écrire le test `test_verify_otp_rejects_any_incorrect_otp`
    - **Property 4 : rejet de tout OTP incorrect**
    - **Validates: Requirements 2.2**
    - Stratégie : deux `st.text(alphabet="0123456789", min_size=6, max_size=6)` avec `assume(otp1 != otp2)`, 100 exemples
    - Mock `get_otp` → `sha256(otp_stored)`, soumettre `otp_submitted`, vérifier `HTTPException(400, code="INVALID_OTP")`

- [ ] 7. Checkpoint final — suite complète au vert
  - Lancer `pytest tests/test_auth_service.py tests/test_otp_hash_properties.py -v`
  - Tous les tests (anciens mis à jour + nouveaux) doivent passer
  - Vérifier qu'aucun test de la suite globale (`pytest`) n'est cassé par les changements

## Notes

- Les tâches 5.x et 6.x sont des sous-tâches de test — les étoiles (`*`) sur 6.1–6.4 indiquent qu'elles sont optionnelles pour un MVP rapide, mais **fortement recommandées** pour la PR
- Les tâches 5.1–5.4 (sans étoile) sont obligatoires : ce sont les tests de couverture minimale exigés par le ticket
- `hypothesis` doit être dans `requirements.txt` — vérifier avant d'écrire les tests ; sinon l'ajouter avec la version épinglée (`hypothesis==6.112.1`)
- Le flag `--tb=short -q` en CI suffit ; pour le debug local, utiliser `-v --hypothesis-show-statistics`
- `_hash_otp` est une fonction privée (préfixe `_`) — elle est importée dans les tests directement depuis `app.core.redis` uniquement pour les tests de propriété ; dans `auth_service.py` elle est importée normalement
