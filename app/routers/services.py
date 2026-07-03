"""
Router Services — endpoints CRUD pour les services d'agence.

Deux catégories d'endpoints :
  1. Endpoints admin (sous /organizations/{org_id}/agencies/{agency_id}/services)
     → Créer, modifier, désactiver un service.
     → Nécessite rôle ADMIN_AGENCY minimum.
  2. Endpoint public (sous /agencies/{agency_id}/services)
     → Lister les services d'une agence pour le client mobile.
     → Accessible avec n'importe quel token valide (get_current_user).

Le mobile appelle GET /agencies/{agency_id}/services pour afficher
les services disponibles avant de prendre un ticket.
"""
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_admin_agency
from app.models.user import User
from app.schemas.service import CreateServiceRequest, UpdateServiceRequest
from app.services.service_service import ServiceService

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Endpoint public — utilisé par le mobile ───────────────────────────────────

@router.get(
    "/agencies/{agency_id}/services",
    summary="Lister les services d'une agence (public mobile)",
)
async def list_services(
    agency_id: str,
    page: int = Query(default=1, ge=1, description="Numéro de page"),
    page_size: int = Query(default=50, ge=1, le=100, description="Éléments par page"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste les services actifs d'une agence.

    Utilisé par le client mobile pour afficher les services
    disponibles avant de prendre un ticket.
    Retourne uniquement les services actifs (is_active=True).
    """
    service = ServiceService(db)
    return await service.list_by_agency(
        agency_id=agency_id,
        page=page,
        page_size=page_size,
        active_only=True,
    )


# ── Endpoints admin — gestion des services ───────────────────────────────────

@router.post(
    "/organizations/{org_id}/agencies/{agency_id}/services",
    summary="Créer un service dans une agence",
    status_code=201,
)
async def create_service(
    org_id: str,
    agency_id: str,
    body: CreateServiceRequest,
    current_user: User = Depends(get_current_admin_agency),  # ADMIN_AGENCY minimum
    db: AsyncSession = Depends(get_db),
):
    """
    Crée un nouveau service dans une agence.
    Nécessite le rôle ADMIN_AGENCY, ADMIN_ORG ou SUPER_ADMIN.

    Un service correspond à une file dédiée (Caisse, Crédit, Consultation...).
    Le préfixe de ticket doit être unique par agence (ex: A, B, VIP).
    """
    # Isolation multi-tenant : un admin_org ne peut gérer que son org
    from fastapi import HTTPException, status
    if (
        current_user.role.value not in ("super_admin",)
        and current_user.org_id
        and current_user.org_id != org_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "Vous ne pouvez pas créer un service dans une autre organisation",
            },
        )

    svc = ServiceService(db)
    result = await svc.create(org_id=org_id, agency_id=agency_id, data=body)
    return {"success": True, "data": result, "message": "Service créé avec succès"}


@router.get(
    "/organizations/{org_id}/agencies/{agency_id}/services",
    summary="Lister tous les services d'une agence (admin)",
)
async def list_services_admin(
    org_id: str,
    agency_id: str,
    page: int = Query(default=1, ge=1, description="Numéro de page"),
    page_size: int = Query(default=50, ge=1, le=100, description="Éléments par page"),
    active_only: bool = Query(default=False, description="Filtrer uniquement les actifs"),
    current_user: User = Depends(get_current_admin_agency),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste tous les services d'une agence, y compris les inactifs.
    Réservé aux admins — pour la gestion et la configuration.
    """
    svc = ServiceService(db)
    return await svc.list_by_agency(
        agency_id=agency_id,
        page=page,
        page_size=page_size,
        active_only=active_only,
    )


@router.get(
    "/organizations/{org_id}/agencies/{agency_id}/services/{service_id}",
    summary="Détail d'un service (admin)",
)
async def get_service(
    org_id: str,
    agency_id: str,
    service_id: str,
    current_user: User = Depends(get_current_admin_agency),
    db: AsyncSession = Depends(get_db),
):
    """Retourne le détail d'un service par son ID."""
    svc = ServiceService(db)
    result = await svc.get_by_id(service_id=service_id, agency_id=agency_id)
    return {"success": True, "data": result}


@router.patch(
    "/organizations/{org_id}/agencies/{agency_id}/services/{service_id}",
    summary="Modifier un service",
)
async def update_service(
    org_id: str,
    agency_id: str,
    service_id: str,
    body: UpdateServiceRequest,
    current_user: User = Depends(get_current_admin_agency),
    db: AsyncSession = Depends(get_db),
):
    """
    Met à jour un service existant (mise à jour partielle).
    Seuls les champs fournis dans le body sont modifiés.
    Nécessite le rôle ADMIN_AGENCY minimum.
    """
    svc = ServiceService(db)
    result = await svc.update(
        service_id=service_id,
        agency_id=agency_id,
        org_id=org_id,
        data=body,
    )
    return {"success": True, "data": result, "message": "Service mis à jour"}


@router.delete(
    "/organizations/{org_id}/agencies/{agency_id}/services/{service_id}",
    summary="Désactiver un service (soft delete)",
)
async def delete_service(
    org_id: str,
    agency_id: str,
    service_id: str,
    current_user: User = Depends(get_current_admin_agency),
    db: AsyncSession = Depends(get_db),
):
    """
    Désactive un service (soft delete).
    Le service n'accepte plus de nouveaux tickets mais les existants restent intacts.
    Nécessite le rôle ADMIN_AGENCY minimum.
    """
    svc = ServiceService(db)
    await svc.delete(
        service_id=service_id,
        agency_id=agency_id,
        org_id=org_id,
    )
    return {"success": True, "message": "Service désactivé"}
