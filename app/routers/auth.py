"""
Router d'authentification — les endpoints /api/v1/auth/...
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth import (
    RegisterPhoneRequest, VerifyOtpRequest,
    RegisterEmailRequest, LoginEmailRequest,
    RefreshTokenRequest
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register/phone", summary="Inscription par téléphone — envoi OTP")
async def register_phone(
    body: RegisterPhoneRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    L'utilisateur entre son numéro → reçoit un SMS avec le code OTP.
    En développement, le code est toujours 123456.
    """
    service = AuthService(db)
    return await service.register_phone(body)


@router.post("/verify-otp", summary="Vérifier le code OTP → obtenir JWT")
async def verify_otp(
    body: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    L'utilisateur entre le code OTP reçu par SMS.
    Si correct → retourne access_token + refresh_token + profil.
    """
    service = AuthService(db)
    return await service.verify_otp(body)


@router.post("/register/email", summary="Inscription par email")
async def register_email(
    body: RegisterEmailRequest,
    db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    return await service.register_email(body)


@router.post("/login", summary="Connexion par email + mot de passe")
async def login_email(
    body: LoginEmailRequest,
    db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    return await service.login_email(body)


@router.post("/refresh", summary="Renouveler le token d'accès")
async def refresh_token(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Le mobile envoie son refresh_token → reçoit un nouvel access_token.
    Appelé automatiquement par le client quand l'access_token expire (15 min).
    """
    service = AuthService(db)
    return await service.refresh_token(body.refresh_token)
