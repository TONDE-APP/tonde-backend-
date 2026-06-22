"""
Service d'authentification — toute la logique de connexion/inscription.

Flux principal :
  1. register_phone(phone) → envoie OTP SMS
  2. verify_otp(phone, otp) → retourne JWT + persiste refresh token en DB

Flux secondaire :
  - register_email / login_email pour les agents et admins
  - refresh_token pour rotation sécurisée (révoque l'ancien, émet le nouveau)
  - logout / logout_all pour révocation de session
"""
import hashlib
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status

from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    generate_otp, verify_token, DEV_OTP,
)
from app.core.redis import (
    save_otp, get_otp, delete_otp,
    increment_otp_attempts, _hash_otp,
)
from app.core.config import settings
from app.schemas.auth import (
    RegisterPhoneRequest, VerifyOtpRequest,
    RegisterEmailRequest, LoginEmailRequest,
    AuthResponse, UserInToken, RefreshResponse,
)

logger = logging.getLogger(__name__)


# ── Helpers privés module-level ───────────────────────────────────────────────
def _hash_token(token: str) -> str:
    """
    Hash SHA-256 d'un JWT refresh token.
    Seule forme autorisée pour le stockage en base — jamais le token en clair.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _get_token_expiry(token: str) -> datetime:
    """
    Extrait la date d'expiration (exp) du payload JWT sans re-vérifier la signature.
    La signature a déjà été vérifiée par verify_token() avant cet appel.
    """
    from jose import jwt as jose_jwt
    payload = jose_jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_exp": False},
    )
    return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Étape 1 : Inscription par téléphone ───────────────────────────────────
    async def register_phone(self, data: RegisterPhoneRequest) -> dict:
        """
        L'utilisateur entre son numéro → reçoit un OTP par SMS.

        Protections :
          - Max 3 demandes SMS par numéro par minute (anti-spam SMS)
          - Numéro bloqué si trop d'échecs OTP précédents

        En développement (ENVIRONMENT=development) :
          - L'OTP est toujours 123456
          - Aucun SMS n'est envoyé

        Returns:
            Dict avec success, message, expires_in_seconds
            En développement : inclut dev_otp pour les tests

        Raises:
            HTTPException 429: Trop de demandes SMS ou numéro bloqué
        """
        phone = data.phone

        otp = DEV_OTP if settings.ENVIRONMENT == "development" else generate_otp()
        await save_otp(phone, otp)
        await self._send_otp_sms(phone, otp)

        response: dict = {
            "success": True,
            "message": "Code OTP envoyé par SMS",
            "otp_sent": True,
            "expires_in_seconds": settings.OTP_EXPIRE_MINUTES * 60,
        }

        if settings.ENVIRONMENT == "development":
            response["dev_otp"] = otp
            logger.debug(f"[DEV] OTP pour {phone}: {otp}")

        return response

    # ── Étape 2 : Vérification OTP ────────────────────────────────────────────
    async def verify_otp(self, data: VerifyOtpRequest) -> AuthResponse:
        """
        Vérifie l'OTP (comparaison de hash SHA-256) et retourne les tokens JWT.
        Crée automatiquement le compte si c'est le premier login.
        Persiste le refresh token en base de données.

        Protections :
          - Numéro bloqué si déjà trop d'échecs → 429 immédiat
          - Max OTP_MAX_ATTEMPTS tentatives par code (défaut 5)
          - Blocage 15 min du numéro après épuisement des tentatives

        Args:
            data: phone + otp saisi par l'utilisateur

        Returns:
            AuthResponse avec access_token, refresh_token, user

        Raises:
            HTTPException 400: OTP expiré ou invalide
            HTTPException 429: Numéro bloqué ou trop de tentatives
        """
        phone = data.phone
        otp = data.otp

        stored_hash = await get_otp(phone)
        if not stored_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "OTP_EXPIRED",
                    "message": "Le code OTP a expiré. Demandez un nouveau code en renvoyant votre numéro.",
                },
            )

        attempts = await increment_otp_attempts(phone)
        if attempts > settings.OTP_MAX_ATTEMPTS:
            # Épuisement total → bloquer le numéro 15 minutes
            await block_phone(phone)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "TOO_MANY_ATTEMPTS", "message": "Trop de tentatives. Demandez un nouveau code."},
            )

        if _hash_otp(otp) != stored_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "PHONE_BLOCKED",
                    "message": (
                        f"Trop de tentatives incorrectes. "
                        f"Ce numéro est bloqué pendant 15 minutes. "
                        f"Si vous n'avez pas demandé ce code, ignorez ce message."
                    ),
                    "retry_after_seconds": PHONE_BLOCK_SECONDS,
                },
            )

        await delete_otp(phone)

        user = await self._get_or_create_user_by_phone(phone)
        user.is_verified = True
        user.last_login = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"Connexion réussie par OTP: {phone} | user_id={user.id}")

        return await self._create_auth_response(user, device_id=data.device_id)

    # ── Inscription par email ─────────────────────────────────────────────────
    async def register_email(self, data: RegisterEmailRequest) -> AuthResponse:
        """
        Inscription directe par email/mot de passe.
        Utilisé principalement par les agents et admins.
        """
        result = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "EMAIL_EXISTS", "message": "Cet email est déjà utilisé"},
            )

        user = User(
            email=data.email,
            name=data.name,
            hashed_password=hash_password(data.password),
            is_verified=True,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"Nouveau compte email: {data.email} | user_id={user.id}")

        return await self._create_auth_response(user, device_id=data.device_id)

    # ── Connexion par email ───────────────────────────────────────────────────
    async def login_email(self, data: LoginEmailRequest) -> AuthResponse:
        """
        Connexion email + mot de passe.

        Raises:
            HTTPException 401: Credentials invalides
            HTTPException 403: Compte désactivé
        """
        result = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.hashed_password or ""):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "Email ou mot de passe incorrect"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ACCOUNT_DISABLED", "message": "Ce compte est désactivé"},
            )

        user.last_login = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"Connexion email: {data.email} | user_id={user.id}")

        return await self._create_auth_response(user, device_id=data.device_id)

    # ── Refresh Token — rotation complète ────────────────────────────────────
    async def refresh_token(self, refresh_token_str: str) -> RefreshResponse:
        """
        Renouvelle l'access token avec rotation sécurisée du refresh token.

        Processus :
          1. Vérifie la signature JWT
          2. Vérifie la présence et validité en base (non révoqué, non expiré)
          3. Révoque l'ancien token
          4. Émet un nouveau refresh token et le persiste en base

        Raises:
            HTTPException 401: Token invalide, absent, révoqué ou expiré
        """
        user_id = verify_token(refresh_token_str, token_type="refresh")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_REFRESH_TOKEN", "message": "Token de rafraîchissement invalide"},
            )

        token_hash = _hash_token(refresh_token_str)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        record = result.scalar_one_or_none()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_REFRESH_TOKEN", "message": "Token de rafraîchissement invalide"},
            )

        if record.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_REVOKED", "message": "Cette session a été révoquée. Reconnectez-vous."},
            )

        # Normaliser expires_at pour la comparaison (SQLite renvoie des datetimes naïfs)
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) >= expires_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_EXPIRED", "message": "Token de rafraîchissement expiré. Reconnectez-vous."},
            )

        # Révoquer l'ancien token
        record.revoked_at = datetime.now(timezone.utc)

        # Émettre les nouveaux tokens
        new_refresh_jwt = create_refresh_token(user_id)
        new_access_jwt = create_access_token(user_id)

        # Persister le nouveau refresh token
        new_record = RefreshToken(
            user_id=user_id,
            token_hash=_hash_token(new_refresh_jwt),
            device_id=record.device_id,
            ip_address=record.ip_address,
            expires_at=_get_token_expiry(new_refresh_jwt),
        )
        self.db.add(new_record)
        await self.db.commit()
        self.db.expunge(new_record)  # évite la re-insertion lors du commit suivant

        return RefreshResponse(
            access_token=new_access_jwt,
            refresh_token=new_refresh_jwt,
        )

    # ── Logout — révocation d'une session ────────────────────────────────────
    async def logout(self, refresh_token_str: str) -> dict:
        """
        Révoque le refresh token fourni — déconnexion d'un device.
        N'affecte pas les autres sessions du même utilisateur.

        Raises:
            HTTPException 401: Token introuvable en base
            HTTPException 400: Token déjà révoqué
        """
        token_hash = _hash_token(refresh_token_str)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        record = result.scalar_one_or_none()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_REFRESH_TOKEN", "message": "Token introuvable"},
            )

        if record.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "TOKEN_ALREADY_REVOKED", "message": "Ce token est déjà révoqué"},
            )

        record.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()

        logger.info(f"Logout — user_id={record.user_id} device={record.device_id}")
        return {"success": True, "message": "Déconnecté avec succès"}

    # ── Logout All — révocation de toutes les sessions ───────────────────────
    async def logout_all(self, user_id: str) -> dict:
        """
        Révoque toutes les sessions actives de l'utilisateur.
        Utile après une compromission de compte.

        Returns:
            Dict avec sessions_revoked (nombre de sessions révoquées)
        """
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        records = result.scalars().all()
        count = len(records)

        for record in records:
            record.revoked_at = now

        await self.db.commit()

        logger.info(f"Logout all — user_id={user_id} sessions_revoked={count}")
        return {
            "success": True,
            "message": "Toutes les sessions révoquées",
            "sessions_revoked": count,
        }

    # ── Helpers privés ────────────────────────────────────────────────────────
    async def _get_or_create_user_by_phone(self, phone: str) -> User:
        """
        Retourne l'utilisateur existant ou en crée un nouveau.
        La première connexion par OTP crée automatiquement le compte.
        """
        result = await self.db.execute(
            select(User).where(User.phone == phone)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(phone=phone)
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            logger.info(f"Nouveau compte créé par OTP: {phone} | user_id={user.id}")

        return user

    async def _create_auth_response(
        self,
        user: User,
        device_id: str | None = None,
        ip_address: str | None = None,
    ) -> AuthResponse:
        """
        Construit la réponse JWT standard après connexion réussie.
        Persiste le refresh token en base de données.

        Args:
            user: Utilisateur authentifié
            device_id: Identifiant du device (optionnel, pour le multi-device)
            ip_address: IP du client (optionnel, pour l'audit)
        """
        refresh_jwt = create_refresh_token(user.id)

        # Si le même device_id existe déjà avec une session active → révoquer l'ancienne
        if device_id:
            await self.db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.device_id == device_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
                .execution_options(synchronize_session="fetch")
            )
            await self.db.flush()

        # Persister le nouveau refresh token (hashé)
        new_record = RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(refresh_jwt),
            device_id=device_id,
            ip_address=ip_address,
            expires_at=_get_token_expiry(refresh_jwt),
        )
        self.db.add(new_record)
        await self.db.commit()
        # Sortir new_record de la session pour éviter qu'il soit re-inséré
        # lors d'un commit ultérieur (important avec expire_on_commit=False)
        self.db.expunge(new_record)

        return AuthResponse(
            access_token=create_access_token(user.id),
            refresh_token=refresh_jwt,
            device_id=device_id,
            user=UserInToken(
                id=user.id,
                name=user.name,
                phone=user.phone,
                email=user.email,
                role=user.role.value,
                language=user.language,
                is_verified=user.is_verified,
            ),
        )

    async def _send_otp_sms(self, phone: str, otp: str) -> None:
        """
        Envoie l'OTP par SMS via Africa's Talking.
        En développement, log seulement — aucun SMS envoyé.
        """
        if settings.ENVIRONMENT == "development":
            logger.debug(f"[DEV] SMS simulé → {phone}: votre code est {otp}")
            return

        try:
            import africastalking
            africastalking.initialize(
                settings.AFRICAS_TALKING_USERNAME,
                settings.AFRICAS_TALKING_API_KEY,
            )
            sms = africastalking.SMS
            message = (
                f"TONDE: Votre code de vérification est {otp}. "
                f"Valide {settings.OTP_EXPIRE_MINUTES} minutes. "
                f"Ne le partagez jamais."
            )
            sms.send(message, [phone], sender_id=settings.AFRICAS_TALKING_SENDER_ID)
            logger.info(f"SMS OTP envoyé: {phone}")
        except Exception as e:
            logger.error(f"Échec envoi SMS OTP vers {phone}: {e}", exc_info=True)
