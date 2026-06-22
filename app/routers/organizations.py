"""
Router Organizations — /api/v1/organizations
Aucune logique métier ici, tout délègue à OrganizationService.
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserRole
from app.schemas.organization import (
    CreateOrganizationRequest,
    UpdateOrganizationRequest,
    OrganizationResponse,
    OrganizationListResponse,
)
from app.services.organization_service import OrganizationService

router = APIRouter()


def _require_admin(current_user: User) -> User:
    """Vérifie que l'utilisateur est admin_org ou super_admin."""
    if current_user.role not in (UserRole.ADMIN_ORG, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Accès réservé aux administrateurs"}
        )
    return current_user


def _check_org_access(current_user: User, target_org_id: str) -> None:
    """
    Vérifie que l'utilisateur peut agir sur l'organisation cible.
    
    Règles:
    - SUPER_ADMIN: peut agir sur toutes les orgs
    - ADMIN_ORG: peut agir sur sa propre org uniquement
    """
    if current_user.role == UserRole.SUPER_ADMIN:
        return  # Accès total
    
    if current_user.role == UserRole.ADMIN_ORG:
        if current_user.org_id != target_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Vous ne pouvez agir que sur votre propre organisation"}
            )
        return


@router.post("", status_code=201)
async def create_organization(
    body: CreateOrganizationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Seul SUPER_ADMIN peut créer des organisations."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Seul un super-admin peut créer des organisations"}
        )
    service = OrganizationService(db)
    result = await service.create(body)
    return {"success": True, "data": result, "message": "Organisation créée"}


@router.get("", response_model=None)
async def list_organizations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """SUPER_ADMIN voit toutes les orgs. ADMIN_ORG ne voit que la sienne."""
    service = OrganizationService(db)
    
    if current_user.role == UserRole.SUPER_ADMIN:
        result = await service.list(page=page, page_size=page_size, active_only=active_only)
    elif current_user.role == UserRole.ADMIN_ORG:
        # Les admin_org ne peuvent lister que leur propre org
        if current_user.org_id:
            result = await service.get_by_id(current_user.org_id)
            result = {"items": [result], "total": 1, "page": 1, "has_next": False}
        else:
            result = {"items": [], "total": 0, "page": 1, "has_next": False}
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Accès réservé aux administrateurs"}
        )
    
    return {"success": True, "data": result}


@router.get("/{org_id}", response_model=None)
async def get_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin(current_user)
    _check_org_access(current_user, org_id)
    service = OrganizationService(db)
    result = await service.get_by_id(org_id)
    return {"success": True, "data": result}


@router.patch("/{org_id}", response_model=None)
async def update_organization(
    org_id: str,
    body: UpdateOrganizationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin(current_user)
    _check_org_access(current_user, org_id)
    service = OrganizationService(db)
    result = await service.update(org_id, body)
    return {"success": True, "data": result, "message": "Organisation mise à jour"}


@router.delete("/{org_id}", status_code=200)
async def delete_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Seul SUPER_ADMIN peut supprimer des organisations."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Seul un super-admin peut supprimer des organisations"}
        )
    service = OrganizationService(db)
    await service.delete(org_id)
    return {"success": True, "message": "Organisation désactivée"}
