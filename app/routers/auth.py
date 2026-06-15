"""
Router d'authentification — les endpoints /api/v1/auth/...
"""
from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth import (
    RegisterPhoneRequest, VerifyOtpRequest,
    RegisterEmailRequest, LoginEmailRequest,
    RefreshTokenRequest
)
from app.services.auth_service import AuthService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/register/phone", summary="Inscription par téléphone — envoi OTP")
@limiter.limit("5/minute")
async def register_phone(
    request: Request,
    body: RegisterPhoneRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    L'utilisateur entre son numéro → reçoit un SMS avec le code OTP.

    Limites de sécurité :
    - Max 5 requêtes/minute par IP (couche réseau)
    - Max 3 demandes SMS/minute par numéro (couche service)
    - Numéro bloqué 15 min après trop d'échecs OTP

    En développement, le code est toujours 123456.
    """
    service = AuthService(db)
    return await service.register_phone(body)


@router.post("/verify-otp", summary="Vérifier le code OTP → obtenir JWT")
@limiter.limit("10/minute")
async def verify_otp(
    request: Request,
    body: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    L'utilisateur entre le code OTP reçu par SMS.

    Limites de sécurité :
    - Max 10 requêtes/minute par IP (couche réseau)
    - Max 5 tentatives par code OTP par numéro (couche service)
    - Blocage 15 min du numéro après épuisement des tentatives
    - Message clair indiquant le nombre de tentatives restantes

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
