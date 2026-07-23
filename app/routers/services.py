"""
Router Services — CRUD des services d'une branch.

Endpoints :
  POST   /api/v1/organizations/{org_id}/branches/{branch_id}/services
  GET    /api/v1/organizations/{org_id}/branches/{branch_id}/services
  GET    /api/v1/branches/{branch_id}/services  ← public pour le mobile
  GET    /api/v1/organizations/{org_id}/branches/{branch_id}/services/{service_id}
  PATCH  /api/v1/organizations/{org_id}/branches/{branch_id}/services/{service_id}
  DELETE /api/v1/organizations/{org_id}/branches/{branch_id}/services/{service_id}

Dépend de : S2-01 (renommage Branch) — utilise /branches/ dans les URLs.
Aucune logique métier ici, tout délègue à ServiceService.
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserRole
from app.services.service_service import ServiceService

router = APIRouter()


# ── Guards ────────────────────────────────────────────────────────────────────

def _require_branch_admin(current_user: User) -> User:
    """ADMIN_AGENCY, ADMIN_ORG ou SUPER_ADMIN requis pour modifier les services."""
    allowed = (UserRole.ADMIN_AGENCY, UserRole.ADMIN_ORG, UserRole.SUPER_ADMIN)
    if current_user.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Accès réservé aux administrateurs"},
        )
    return current_user


def _check_org_access(current_user: User, target_org_id: str) -> None:
    """Vérifie que l'utilisateur peut agir sur l'organisation cible."""
    if current_user.role == UserRole.SUPER_ADMIN:
        return
    if current_user.org_id != target_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Vous ne pouvez agir que sur votre propre organisation"},
        )


# ── Endpoints protégés (admin) ────────────────────────────────────────────────

@router.post(
    "/organizations/{org_id}/branches/{branch_id}/services",
    status_code=201,
    summary="Créer un service dans une branch",
)
async def create_service(
    org_id: str,
    branch_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Crée un service dans une branch. Réservé aux admins."""
    _require_branch_admin(current_user)
    _check_org_access(current_user, org_id)
    svc = ServiceService(db)
    result = await svc.create(org_id=org_id, branch_id=branch_id, data=body)
    return {"success": True, "data": result, "message": "Service créé"}


@router.get(
    "/organizations/{org_id}/branches/{branch_id}/services",
    summary="Lister les services d'une branch (admin)",
)
async def list_services_admin(
    org_id: str,
    branch_id: str,
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Liste les services d'une branch. Réservé aux admins."""
    _require_branch_admin(current_user)
    _check_org_access(current_user, org_id)
    svc = ServiceService(db)
    items = await svc.list(branch_id=branch_id, org_id=org_id, active_only=active_only)
    return {"success": True, "data": items}


@router.get(
    "/organizations/{org_id}/branches/{branch_id}/services/{service_id}",
    summary="Détail d'un service",
)
async def get_service(
    org_id: str,
    branch_id: str,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_branch_admin(current_user)
    _check_org_access(current_user, org_id)
    svc = ServiceService(db)
    result = await svc.get_by_id(service_id=service_id, branch_id=branch_id, org_id=org_id)
    return {"success": True, "data": result}


@router.patch(
    "/organizations/{org_id}/branches/{branch_id}/services/{service_id}",
    summary="Mettre à jour un service",
)
async def update_service(
    org_id: str,
    branch_id: str,
    service_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_branch_admin(current_user)
    _check_org_access(current_user, org_id)
    svc = ServiceService(db)
    result = await svc.update(service_id=service_id, branch_id=branch_id, org_id=org_id, data=body)
    return {"success": True, "data": result, "message": "Service mis à jour"}


@router.delete(
    "/organizations/{org_id}/branches/{branch_id}/services/{service_id}",
    summary="Désactiver un service",
)
async def delete_service(
    org_id: str,
    branch_id: str,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_branch_admin(current_user)
    _check_org_access(current_user, org_id)
    svc = ServiceService(db)
    await svc.delete(service_id=service_id, branch_id=branch_id, org_id=org_id)
    return {"success": True, "message": "Service désactivé"}


# ── Endpoint public (mobile) ──────────────────────────────────────────────────

@router.get(
    "/branches/{branch_id}/services",
    summary="Lister les services d'une branch (public — mobile)",
)
async def list_services_public(
    branch_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Liste les services actifs d'une branch.
    Accessible sans authentification — utilisé par le mobile
    pour afficher les services disponibles avant de prendre un ticket.
    """
    svc = ServiceService(db)
    items = await svc.list(branch_id=branch_id, org_id=None, active_only=True)
    return {"success": True, "data": items}
