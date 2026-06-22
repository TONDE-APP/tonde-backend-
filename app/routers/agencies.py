"""
Router Agencies (Branches) — /api/v1/agencies
Aucune logique métier ici, tout délègue à AgencyService.
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserRole
from app.schemas.agency import (
    CreateAgencyRequest,
    UpdateAgencyRequest,
    AgencyListResponse,
)
from app.services.agency_service import AgencyService

router = APIRouter()


def _require_agency_admin(current_user: User) -> User:
    """Vérifie que l'utilisateur a un rôle d'administration d'agence ou supérieur."""
    allowed = (
        UserRole.ADMIN_AGENCY,
        UserRole.ADMIN_ORG,
        UserRole.SUPER_ADMIN,
    )
    if current_user.role not in allowed:
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
    - ADMIN_AGENCY: ne peut PAS créer d'agences dans d'autres orgs (escalade de privilèges)
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
    
    # ADMIN_AGENCY ne devrait pas pouvoir créer/modifier des agences dans d'autres orgs
    if current_user.role == UserRole.ADMIN_AGENCY:
        if current_user.org_id != target_org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Vous ne pouvez gérer que les agences de votre organisation"}
            )
        return


@router.post("/{org_id}/agencies", status_code=201)
async def create_agency(
    org_id: str,
    body: CreateAgencyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_agency_admin(current_user)
    _check_org_access(current_user, org_id)
    service = AgencyService(db)
    result = await service.create(org_id, body, current_user.org_id)
    return {"success": True, "data": result, "message": "Agence créée"}


@router.get("/{org_id}/agencies")
async def list_agencies(
    org_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_agency_admin(current_user)
    _check_org_access(current_user, org_id)
    service = AgencyService(db)
    result = await service.list(
        caller_org_id=current_user.org_id,
        org_id=org_id,
        page=page,
        page_size=page_size,
        active_only=active_only,
    )
    return {"success": True, "data": result}


@router.get("/{org_id}/agencies/{agency_id}")
async def get_agency(
    org_id: str,
    agency_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_agency_admin(current_user)
    _check_org_access(current_user, org_id)
    service = AgencyService(db)
    result = await service.get_by_id(agency_id, current_user.org_id)
    return {"success": True, "data": result}


@router.patch("/{org_id}/agencies/{agency_id}")
async def update_agency(
    org_id: str,
    agency_id: str,
    body: UpdateAgencyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_agency_admin(current_user)
    _check_org_access(current_user, org_id)
    service = AgencyService(db)
    result = await service.update(agency_id, body, current_user.org_id)
    return {"success": True, "data": result, "message": "Agence mise à jour"}


@router.delete("/{org_id}/agencies/{agency_id}")
async def delete_agency(
    org_id: str,
    agency_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_agency_admin(current_user)
    _check_org_access(current_user, org_id)
    service = AgencyService(db)
    await service.delete(agency_id, current_user.org_id)
    return {"success": True, "message": "Agence désactivée"}
