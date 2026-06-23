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
    increment_otp_attempts, _hash_otp,
    is_phone_blocked, block_phone,
    increment_register_attempts, PHONE_REGISTER_MAX, PHONE_BLOCK_SECONDS,
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

        # Couche 1 — Numéro bloqué suite à trop d'échecs OTP ?
        blocked, seconds_left = await is_phone_blocked(phone)
        if blocked:
            minutes_left = (seconds_left + 59) // 60
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "PHONE_BLOCKED",
                    "message": (
                        f"Ce numéro est temporairement bloqué suite à trop de tentatives incorrectes. "
                        f"Réessayez dans {minutes_left} minute(s)."
                    ),
                    "retry_after_seconds": seconds_left,
                },
            )

        # Couche 2 — Trop de demandes de SMS sur ce numéro ?
        sms_count = await increment_register_attempts(phone)
        if sms_count > PHONE_REGISTER_MAX:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "SMS_RATE_LIMIT",
                    "message": (
                        f"Trop de demandes de code pour ce numéro. "
                        f"Vous pouvez demander au maximum {PHONE_REGISTER_MAX} codes par minute. "
                        f"Attendez avant de réessayer."
                    ),
                    "retry_after_seconds": 60,
                },
            )

        # Générer l'OTP
        otp = DEV_OTP if settings.ENVIRONMENT == "development" else generate_otp()

        # Stocker dans Redis avec TTL (réinitialise aussi le compteur d'échecs)
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

        # Couche 1 — Numéro déjà bloqué ?
        blocked, seconds_left = await is_phone_blocked(phone)
        if blocked:
            minutes_left = (seconds_left + 59) // 60
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "PHONE_BLOCKED",
                    "message": (
                        f"Ce numéro est temporairement bloqué suite à trop de tentatives incorrectes. "
                        f"Réessayez dans {minutes_left} minute(s)."
                    ),
                    "retry_after_seconds": seconds_left,
                },
            )

        # Couche 2 — OTP existe encore dans Redis ?
        stored_otp = await get_otp(phone)
        if not stored_otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "OTP_EXPIRED",
                    "message": "Le code OTP a expiré. Demandez un nouveau code en renvoyant votre numéro.",
                },
            )

        # Couche 3 — Incrémenter et vérifier le compteur de tentatives
        attempts = await increment_otp_attempts(phone)
        if attempts > settings.OTP_MAX_ATTEMPTS:
            # Épuisement total → bloquer le numéro 15 minutes
            await block_phone(phone)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
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

        # Couche 4 — Comparer les hash SHA-256 (jamais les valeurs en clair)
        if _hash_otp(otp) != stored_otp:
            remaining = settings.OTP_MAX_ATTEMPTS - attempts
            if remaining > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "INVALID_OTP",
                        "message": (
                            f"Code incorrect. Il vous reste {remaining} tentative(s) "
                            f"avant le blocage temporaire du numéro."
                        ),
                        "attempts_remaining": remaining,
                    },
                )
            else:
                # Dernière tentative épuisée → bloquer maintenant
                await block_phone(phone)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "PHONE_BLOCKED",
                        "message": (
                            "Code incorrect. Vous avez épuisé toutes vos tentatives. "
                            "Ce numéro est bloqué pendant 15 minutes."
                        ),
                        "retry_after_seconds": PHONE_BLOCK_SECONDS,
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
        Recharge le user depuis la DB et vérifie qu'il est toujours actif.

        Raises:
            HTTPException 401: Refresh token invalide, expiré, ou user désactivé
        """
        user_id = verify_token(refresh_token, token_type="refresh")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_REFRESH_TOKEN", "message": "Token de rafraîchissement invalide"},
            )

        # Recharger le user depuis la DB — un compte suspendu ne doit pas pouvoir rafraîchir
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_REFRESH_TOKEN", "message": "Utilisateur introuvable"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ACCOUNT_DISABLED", "message": "Ce compte a été désactivé"},
            )

        new_access_token = create_access_token(user.id)
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
