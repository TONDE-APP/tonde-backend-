"""
Service d'authentification — toute la logique de connexion/inscription.

Flux principal :
  1. register_phone(phone) → envoie OTP SMS
  2. verify_otp(phone, otp) → retourne JWT

Flux secondaire :
  - register_email / login_email pour les agents et admins
  - refresh_token pour renouveler l'access token
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.user import User
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    generate_otp, verify_token, DEV_OTP,
)
from app.core.redis import (
    save_otp, get_otp, delete_otp,
    increment_otp_attempts,
)
from app.core.config import settings
from app.schemas.auth import (
    RegisterPhoneRequest, VerifyOtpRequest,
    RegisterEmailRequest, LoginEmailRequest,
    AuthResponse, UserInToken,
)

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Étape 1 : Inscription par téléphone ───────────────────────────────────
    async def register_phone(self, data: RegisterPhoneRequest) -> dict:
        """
        L'utilisateur entre son numéro → reçoit un OTP par SMS.

        En développement (ENVIRONMENT=development) :
          - L'OTP est toujours 123456
          - Aucun SMS n'est envoyé

        Returns:
            Dict avec success, message, expires_in_seconds
            En développement : inclut dev_otp pour les tests
        """
        phone = data.phone

        # Générer l'OTP
        otp = DEV_OTP if settings.ENVIRONMENT == "development" else generate_otp()

        # Stocker dans Redis avec TTL
        await save_otp(phone, otp)

        # Envoyer le SMS
        await self._send_otp_sms(phone, otp)

        response: dict = {
            "success": True,
            "message": "Code OTP envoyé par SMS",
            "otp_sent": True,
            "expires_in_seconds": settings.OTP_EXPIRE_MINUTES * 60,
        }

        # Exposer l'OTP UNIQUEMENT en développement local
        # Ne jamais exposer en staging ou production
        if settings.ENVIRONMENT == "development":
            response["dev_otp"] = otp
            logger.debug(f"[DEV] OTP pour {phone}: {otp}")

        return response

    # ── Étape 2 : Vérification OTP ────────────────────────────────────────────
    async def verify_otp(self, data: VerifyOtpRequest) -> AuthResponse:
        """
        Vérifie l'OTP et retourne les tokens JWT.
        Crée automatiquement le compte si c'est le premier login.

        Args:
            data: phone + otp saisi par l'utilisateur

        Returns:
            AuthResponse avec access_token, refresh_token, user

        Raises:
            HTTPException 400: OTP expiré ou invalide
            HTTPException 429: Trop de tentatives
        """
        phone = data.phone
        otp = data.otp

        # Vérifier que l'OTP existe encore dans Redis
        stored_otp = await get_otp(phone)
        if not stored_otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "OTP_EXPIRED", "message": "Le code OTP a expiré. Demandez un nouveau code."},
            )

        # Incrémenter et vérifier le compteur de tentatives
        attempts = await increment_otp_attempts(phone)
        if attempts > settings.OTP_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "TOO_MANY_ATTEMPTS", "message": "Trop de tentatives. Demandez un nouveau code."},
            )

        # Comparer les OTP
        if otp != stored_otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_OTP",
                    "message": f"Code incorrect. Tentative {attempts}/{settings.OTP_MAX_ATTEMPTS}",
                },
            )

        # OTP correct → supprimer de Redis
        await delete_otp(phone)

        # Chercher ou créer l'utilisateur
        user = await self._get_or_create_user_by_phone(phone)
        user.is_verified = True
        user.last_login = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"Connexion réussie par OTP: {phone} | user_id={user.id}")

        return self._create_auth_response(user)

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

        return self._create_auth_response(user)

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

        logger.info(f"Connexion email: {data.email} | user_id={user.id}")

        return self._create_auth_response(user)

    # ── Refresh Token ─────────────────────────────────────────────────────────
    async def refresh_token(self, refresh_token: str) -> dict:
        """
        Renouvelle l'access token à partir d'un refresh token valide.

        Raises:
            HTTPException 401: Refresh token invalide ou expiré
        """
        user_id = verify_token(refresh_token, token_type="refresh")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_REFRESH_TOKEN", "message": "Token de rafraîchissement invalide"},
            )

        new_access_token = create_access_token(user_id)
        return {
            "success": True,
            "access_token": new_access_token,
            "token_type": "bearer",
        }

    # ── Helpers privés ────────────────────────────────────────────────────────
    async def _get_or_create_user_by_phone(self, phone: str) -> User:
        """
        Retourne l'utilisateur existant ou en crée un nouveau.
        C'est le mécanisme d'inscription implicite de TONDE :
        la première connexion par OTP crée automatiquement le compte.
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

    def _create_auth_response(self, user: User) -> AuthResponse:
        """Construit la réponse JWT standard après connexion réussie."""
        return AuthResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
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
        En production, lève une alerte si le SMS échoue mais ne bloque pas.
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
            # Ne pas bloquer l'inscription si le SMS échoue
            # TODO Sprint 1 : ajouter retry avec queue Redis
            logger.error(f"Échec envoi SMS OTP vers {phone}: {e}", exc_info=True)
