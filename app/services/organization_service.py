"""
OrganizationService — Logique métier pour la gestion des organisations.

Pattern : Router → Service → Model
Toutes les opérations DB passent par ce service.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException

from app.models.organization import Organization
from app.schemas.organization import (
    CreateOrganizationRequest,
    UpdateOrganizationRequest,
    OrganizationResponse,
    OrganizationListResponse,
)


class OrganizationService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: CreateOrganizationRequest) -> OrganizationResponse:
        """
        Crée une nouvelle organisation.

        Args:
            data: Données de création (name, slug, sector, ...)

        Returns:
            OrganizationResponse avec l'organisation créée

        Raises:
            HTTPException 409: Si le slug est déjà utilisé
        """
        existing = await self.db.execute(
            select(Organization).where(Organization.slug == data.slug)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail={"code": "SLUG_TAKEN", "message": f"Le slug '{data.slug}' est déjà utilisé"}
            )

        org = Organization(**data.model_dump())
        self.db.add(org)
        await self.db.commit()
        await self.db.refresh(org)
        return OrganizationResponse.model_validate(org)

    async def get_by_id(self, org_id: str) -> OrganizationResponse:
        """
        Récupère une organisation par son ID.

        Args:
            org_id: UUID de l'organisation

        Returns:
            OrganizationResponse

        Raises:
            HTTPException 404: Si l'organisation n'existe pas
        """
        result = await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = result.scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=404,
                detail={"code": "ORG_NOT_FOUND", "message": "Organisation introuvable"}
            )
        return OrganizationResponse.model_validate(org)

    async def list(
        self, page: int = 1, page_size: int = 20, active_only: bool = False
    ) -> OrganizationListResponse:
        """
        Liste toutes les organisations avec pagination.

        Args:
            page: Numéro de page (commence à 1)
            page_size: Nombre d'éléments par page (max 100)
            active_only: Si True, retourne uniquement les organisations actives

        Returns:
            OrganizationListResponse avec items et métadonnées de pagination
        """
        page_size = min(page_size, 100)
        offset = (page - 1) * page_size

        query = select(Organization)
        count_query = select(func.count(Organization.id))

        if active_only:
            query = query.where(Organization.is_active == True)  # noqa: E712
            count_query = count_query.where(Organization.is_active == True)  # noqa: E712

        query = query.order_by(Organization.created_at.desc()).offset(offset).limit(page_size)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        orgs = result.scalars().all()

        return OrganizationListResponse(
            items=[OrganizationResponse.model_validate(o) for o in orgs],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update(self, org_id: str, data: UpdateOrganizationRequest) -> OrganizationResponse:
        """
        Met à jour une organisation existante.

        Args:
            org_id: UUID de l'organisation à modifier
            data: Champs à mettre à jour (seuls les champs fournis sont modifiés)

        Returns:
            OrganizationResponse mise à jour

        Raises:
            HTTPException 404: Si l'organisation n'existe pas
        """
        result = await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = result.scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=404,
                detail={"code": "ORG_NOT_FOUND", "message": "Organisation introuvable"}
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(org, field, value)

        await self.db.commit()
        await self.db.refresh(org)
        return OrganizationResponse.model_validate(org)

    async def delete(self, org_id: str) -> None:
        """
        Supprime une organisation (suppression douce via is_active=False).

        On ne supprime jamais physiquement une organisation en production
        pour préserver l'historique des tickets et utilisateurs associés.

        Args:
            org_id: UUID de l'organisation à désactiver

        Raises:
            HTTPException 404: Si l'organisation n'existe pas
        """
        result = await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = result.scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=404,
                detail={"code": "ORG_NOT_FOUND", "message": "Organisation introuvable"}
            )

        org.is_active = False
        await self.db.commit()
