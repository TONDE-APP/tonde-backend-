# Implementation Plan — TASK-02 : Refresh Token persisté en base de données

## Overview

Passer le refresh token de stateless à stateful en 6 étapes séquentielles.
Surface de changement : 1 nouveau modèle, 1 migration Alembic, 4 fichiers modifiés.

Branche Git : `feat/refresh-token-db`

---

## Tasks

- [ ] 1. Créer `app/models/refresh_token.py`
  - Importer `uuid`, `datetime`, `timezone`, `Mapped`, `mapped_column`, `String`, `DateTime`, `ForeignKey`, `Base`
  - Déclarer la classe `RefreshToken(Base)` avec `__tablename__ = "refresh_tokens"`
  - Champs obligatoires (voir design.md — section Data Models) :
    - `id: Mapped[str]` — UUID PK, `default=lambda: str(uuid.uuid4())`
    - `user_id: Mapped[str]` — FK `users.id` ON DELETE CASCADE, `index=True`
    - `token_hash: Mapped[str]` — `String(64)`, `unique=True` (SHA-256 = 64 hex chars)
    - `device_id: Mapped[str | None]` — nullable, `index=True`
    - `ip_address: Mapped[str | None]` — `String(45)`, nullable (IPv4 ou IPv6)
    - `expires_at: Mapped[datetime]` — `DateTime(timezone=True)`
    - `revoked_at: Mapped[datetime | None]` — `DateTime(timezone=True)`, nullable
    - `created_at: Mapped[datetime]` — default `datetime.now(timezone.utc)`
  - Ajouter `__table_args__` avec l'index composite `(user_id, revoked_at)` nommé `ix_refresh_tokens_user_active`
  - Ajouter `def __repr__` pour la lisibilité
  - _Requirements: 1.2, 1.3, 1.4_

- [ ] 2. Importer `RefreshToken` dans `app/models/__init__.py`
  - Ajouter `from app.models.refresh_token import RefreshToken` pour que `Base.metadata` connaisse la table
  - Vérifier que `conftest.py` crée bien la table dans SQLite en mémoire (via `Base.metadata.create_all`)
  - _Requirements: 1.5_

- [ ] 3. Générer et vérifier la migration Alembic
  - Commande : `alembic revision --autogenerate -m "add_refresh_tokens_table"`
  - Ouvrir le fichier généré et vérifier que `upgrade()` contient bien `op.create_table("refresh_tokens", ...)`
  - Vérifier la présence de l'index composite et de la contrainte FK CASCADE
  - Ne pas appliquer `alembic upgrade head` avant d'avoir vérifié le contenu
  - _Requirements: 1.5_

- [ ] 4. Ajouter les helpers privés et modifier `_create_auth_response()` dans `app/services/auth_service.py`
  - [ ] 4.1 Ajouter l'import `hashlib` et `RefreshToken` en tête du fichier
  - [ ] 4.2 Ajouter la fonction helper privée `_hash_token(token: str) -> str`
    ```python
    def _hash_token(token: str) -> str:
        """Hash SHA-256 d'un token JWT. Seule forme autorisée en base."""
        return hashlib.sha256(token.encode()).hexdigest()
    ```
  - [ ] 4.3 Ajouter la fonction helper privée `_get_token_expiry(token: str) -> datetime`
    ```python
    def _get_token_expiry(token: str) -> datetime:
        """Extrait expires_at depuis le payload JWT sans re-vérifier la signature."""
        from jose import jwt as jose_jwt
        payload = jose_jwt.decode(
            token, settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    ```
  - [ ] 4.4 Transformer `_create_auth_response()` en méthode `async`
    - Nouvelle signature : `async def _create_auth_response(self, user: User, device_id: str | None = None, ip_address: str | None = None) -> AuthResponse`
    - Créer le `refresh_token` JWT via `create_refresh_token(user.id)` (inchangé)
    - Calculer `token_hash = _hash_token(refresh_jwt)`
    - Extraire `expires_at = _get_token_expiry(refresh_jwt)`
    - Si `device_id` fourni : révoquer l'ancienne session du même device
      ```python
      await self.db.execute(
          update(RefreshToken)
          .where(RefreshToken.user_id == user.id, RefreshToken.device_id == device_id, RefreshToken.revoked_at.is_(None))
          .values(revoked_at=datetime.now(timezone.utc))
      )
      ```
    - Insérer la nouvelle ligne `RefreshToken`
    - Retourner `AuthResponse` avec `device_id` inclus
  - [ ] 4.5 Mettre à jour tous les appels `_create_auth_response()` en `await self._create_auth_response(...)`
    - `verify_otp` : passer `data.device_id` et extraire `ip_address` depuis le contexte (laisser `None` pour l'instant)
    - `register_email` : idem
    - `login_email` : idem
  - _Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 8.1, 8.2_

- [ ] 5. Réécrire `refresh_token()` avec rotation complète
  - Nouvelle signature : `async def refresh_token(self, refresh_token_str: str) -> RefreshResponse`
  - Étapes dans l'ordre (voir design.md — diagramme de séquence) :
    1. `user_id = verify_token(refresh_token_str, token_type="refresh")` → HTTP 401 si None
    2. `token_hash = _hash_token(refresh_token_str)`
    3. `SELECT * FROM refresh_tokens WHERE token_hash = ?` → HTTP 401 `INVALID_REFRESH_TOKEN` si absent
    4. Si `record.revoked_at IS NOT NULL` → HTTP 401 `TOKEN_REVOKED`
    5. Si `record.expires_at < now()` → HTTP 401 `TOKEN_EXPIRED`
    6. `record.revoked_at = datetime.now(timezone.utc)` (révoquer l'ancien)
    7. `new_refresh_jwt = create_refresh_token(user_id)` + `new_access_jwt = create_access_token(user_id)`
    8. Insérer nouveau `RefreshToken` (même `device_id`, même `ip_address` que l'ancien)
    9. Retourner `RefreshResponse(access_token=new_access_jwt, refresh_token=new_refresh_jwt)`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 6. Ajouter `logout()` et `logout_all()` dans `AuthService`
  - [ ] 6.1 Implémenter `logout(refresh_token_str: str) -> dict`
    ```python
    async def logout(self, refresh_token_str: str) -> dict:
        """Révoque le refresh token fourni — déconnexion d'un device."""
        token_hash = _hash_token(refresh_token_str)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(401, detail={"code": "INVALID_REFRESH_TOKEN", ...})
        if record.revoked_at is not None:
            raise HTTPException(400, detail={"code": "TOKEN_ALREADY_REVOKED", ...})
        record.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()
        return {"success": True, "message": "Déconnecté avec succès"}
    ```
  - [ ] 6.2 Implémenter `logout_all(user_id: str) -> dict`
    ```python
    async def logout_all(self, user_id: str) -> dict:
        """Révoque toutes les sessions actives de l'utilisateur."""
        result = await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
            .returning(RefreshToken.id)
        )
        count = len(result.fetchall())
        await self.db.commit()
        return {"success": True, "message": "Toutes les sessions révoquées", "sessions_revoked": count}
    ```
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3_

- [ ] 7. Mettre à jour `app/schemas/auth.py`
  - Ajouter `device_id: str | None = None` dans `VerifyOtpRequest`, `RegisterEmailRequest`, `LoginEmailRequest`
  - Ajouter `device_id: str | None = None` dans `AuthResponse`
  - Créer `LogoutRequest(BaseModel)` avec `refresh_token: str`
  - Créer `RefreshResponse(BaseModel)` avec `success: bool = True`, `access_token: str`, `refresh_token: str`, `token_type: str = "bearer"`
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 8. Ajouter les endpoints dans `app/routers/auth.py`
  - Ajouter `POST /logout` :
    ```python
    @router.post("/logout", summary="Déconnexion — révoquer le refresh token")
    async def logout(body: LogoutRequest, db: AsyncSession = Depends(get_db)):
        service = AuthService(db)
        return await service.logout(body.refresh_token)
    ```
  - Ajouter `POST /logout/all` :
    ```python
    @router.post("/logout/all", summary="Déconnexion de tous les appareils")
    async def logout_all(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        service = AuthService(db)
        return await service.logout_all(current_user.id)
    ```
  - Mettre à jour `POST /refresh` pour importer et retourner `RefreshResponse`
  - Importer `LogoutRequest` depuis `app.schemas.auth`
  - _Requirements: 4.5, 5.4_

- [ ] 9. Checkpoint — tests existants au vert
  - Lancer `pytest tests/test_auth_service.py -v --tb=short`
  - Corriger les erreurs dues à la transformation de `_create_auth_response` en `async`
  - Vérifier que `test_refresh_token_success` et `test_refresh_token_invalid_raises_401` passent encore

- [ ] 10. Écrire les nouveaux tests dans `tests/test_auth_service.py`
  - [ ] 10.1 `test_logout_revokes_token`
    - Login → obtenir refresh_token → appeler `service.logout(refresh_token)` → vérifier `revoked_at` non NULL en DB
    - _Requirements: 4.1_
  - [ ] 10.2 `test_revoked_token_rejected_on_refresh`
    - Login → révoquer le token via `logout()` → appeler `service.refresh_token(token)` → HTTP 401 `TOKEN_REVOKED`
    - _Requirements: 3.3_
  - [ ] 10.3 `test_rotation_invalidates_old_token`
    - Login → appeler `refresh_token(old_token)` → vérifier que `old_token` est révoqué ET que `new_token != old_token`
    - _Requirements: 3.4_
  - [ ] 10.4 `test_multi_device_independent_sessions`
    - Login deux fois avec `device_id="phone"` et `device_id="tablet"` → vérifier 2 sessions actives → `logout(phone_token)` → vérifier 1 session active (tablet)
    - _Requirements: 6.1, 6.3_
  - [ ] 10.5 `test_logout_all_revokes_all_sessions`
    - Login 3 fois → `logout_all(user.id)` → vérifier `sessions_revoked == 3` et 0 sessions actives
    - _Requirements: 5.1, 5.3_
  - [ ] 10.6 `test_token_not_in_db_rejected`
    - Générer un JWT valide `create_refresh_token("fake-user-id")` sans l'insérer en DB → `refresh_token(jwt)` → HTTP 401 `INVALID_REFRESH_TOKEN`
    - _Requirements: 3.2_
  - [ ] 10.7 `test_device_id_replaces_existing_session`
    - Login avec `device_id="phone"` → login à nouveau avec `device_id="phone"` → vérifier 1 seule session active pour ce device
    - _Requirements: 6.2_

- [ ] 11. Checkpoint final — tous les tests au vert
  - Lancer `pytest tests/ -v --tb=short`
  - Vérifier que les tests existants (auth, ticket, agency, organization) passent toujours
  - Vérifier que les 7 nouveaux tests passent

## Notes

- `_create_auth_response()` devient `async` — tous les appelants doivent être mis à jour avec `await`
- `update()` de SQLAlchemy 2.0 s'importe depuis `sqlalchemy` : `from sqlalchemy import update`
- Ne jamais logger le `refresh_token` brut — logger uniquement les `user_id` et `device_id`
- Avant de commencer : `git checkout main && git pull && git checkout -b feat/refresh-token-db`
