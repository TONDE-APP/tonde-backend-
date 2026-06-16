"""
AgencyService — Logique métier pour la gestion des agences (Branches).

Règle de sécurité absolue : toute opération filtre par org_id.
Un admin ne peut voir et modifier que les agences de son organisation.

Pattern : Router → Service → Model
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException

from app.models.agency import Agency
from app.models.organization import Organization
from app.schemas.agency import (
    CreateAgencyRequest,
    UpdateAgencyRequest,
    AgencyResponse,
    AgencyListResponse,
)


class AgencyService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _verify_org_exists(self, org_id: str) -> None:
        """Vérifie que l'organisation existe et est active."""
        result = await self.db.execute(
            select(Organization).where(
                Organization.id == org_id,
                Organization.is_active == True,  # noqa: E712
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=404,
                detail={"code": "ORG_NOT_FOUND", "message": "Organisation introuvable ou inactive"}
            )

    async def create(
        self, org_id: str, data: CreateAgencyRequest, caller_org_id: str | None
    ) -> AgencyResponse:
        """
        Crée une nouvelle agence rattachée à une organisation.

        Args:
            org_id: ID de l'organisation cible
            data: Données de création de l'agence
            caller_org_id: org_id de l'utilisateur appelant (None = super_admin)

        Returns:
            AgencyResponse avec l'agence créée

        Raises:
            HTTPException 403: Si l'appelant tente de créer dans une org qui n'est pas la sienne
            HTTPException 404: Si l'organisation n'existe pas
            HTTPException 409: Si le slug est déjà utilisé
        """
        # Isolation multi-tenant : un admin_org ne peut créer que dans son org
        if caller_org_id is not None and caller_org_id != org_id:
            raise HTTPException(
                status_code=403,
                detail={"code": "FORBIDDEN", "message": "Vous ne pouvez pas créer une agence dans une autre organisation"}
            )

        await self._verify_org_exists(org_id)

        existing = await self.db.execute(
            select(Agency).where(Agency.slug == data.slug)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail={"code": "SLUG_TAKEN", "message": f"Le slug '{data.slug}' est déjà utilisé"}
            )

        agency = Agency(org_id=org_id, **data.model_dump())
        self.db.add(agency)
        await self.db.commit()
        await self.db.refresh(agency)
        return AgencyResponse.model_validate(agency)

    async def get_by_id(self, agency_id: str, caller_org_id: str | None) -> AgencyResponse:
        """
        Récupère une agence par son ID.

        Args:
            agency_id: UUID de l'agence
            caller_org_id: org_id de l'utilisateur (None = super_admin, voit tout)

        Returns:
            AgencyResponse

        Raises:
            HTTPException 404: Si l'agence n'existe pas ou n'appartient pas à l'org de l'appelant
        """
        query = select(Agency).where(Agency.id == agency_id)

        # Isolation multi-tenant : filtrer par org_id sauf pour super_admin
        if caller_org_id is not None:
            query = query.where(Agency.org_id == caller_org_id)

        result = await self.db.execute(query)
        agency = result.scalar_one_or_none()
        if not agency:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENCY_NOT_FOUND", "message": "Agence introuvable"}
            )
        return AgencyResponse.model_validate(agency)

    async def list(
        self,
        caller_org_id: str | None,
        org_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
        active_only: bool = False,
    ) -> AgencyListResponse:
        """
        Liste les agences avec pagination.

        Args:
            caller_org_id: org_id de l'appelant — force le filtre multi-tenant
            org_id: filtre optionnel par org (super_admin seulement)
            page: numéro de page
            page_size: éléments par page (max 100)
            active_only: si True, retourne uniquement les agences actives

        Returns:
            AgencyListResponse avec items et métadonnées de pagination
        """
        page_size = min(page_size, 100)
        offset = (page - 1) * page_size

        query = select(Agency)
        count_query = select(func.count(Agency.id))

        # Isolation multi-tenant stricte
        effective_org_id = caller_org_id if caller_org_id is not None else org_id
        if effective_org_id:
            query = query.where(Agency.org_id == effective_org_id)
            count_query = count_query.where(Agency.org_id == effective_org_id)

        if active_only:
            query = query.where(Agency.is_active == True)  # noqa: E712
            count_query = count_query.where(Agency.is_active == True)  # noqa: E712

        query = query.order_by(Agency.created_at.desc()).offset(offset).limit(page_size)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        agencies = result.scalars().all()

        return AgencyListResponse(
            items=[AgencyResponse.model_validate(a) for a in agencies],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update(
        self, agency_id: str, data: UpdateAgencyRequest, caller_org_id: str | None
    ) -> AgencyResponse:
        """
        Met à jour une agence existante.

        Args:
            agency_id: UUID de l'agence à modifier
            data: Champs à mettre à jour (seuls les champs fournis sont modifiés)
            caller_org_id: org_id de l'appelant pour vérification d'appartenance

        Returns:
            AgencyResponse mise à jour

        Raises:
            HTTPException 404: Si l'agence n'existe pas ou n'appartient pas à l'org
        """
        query = select(Agency).where(Agency.id == agency_id)
        if caller_org_id is not None:
            query = query.where(Agency.org_id == caller_org_id)

        result = await self.db.execute(query)
        agency = result.scalar_one_or_none()
        if not agency:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENCY_NOT_FOUND", "message": "Agence introuvable"}
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(agency, field, value)

        await self.db.commit()
        await self.db.refresh(agency)
        return AgencyResponse.model_validate(agency)

    async def delete(self, agency_id: str, caller_org_id: str | None) -> None:
        """
        Désactive une agence (soft delete).

        Args:
            agency_id: UUID de l'agence à désactiver
            caller_org_id: org_id de l'appelant pour vérification d'appartenance

        Raises:
            HTTPException 404: Si l'agence n'existe pas ou n'appartient pas à l'org
        """
        query = select(Agency).where(Agency.id == agency_id)
        if caller_org_id is not None:
            query = query.where(Agency.org_id == caller_org_id)

        result = await self.db.execute(query)
        agency = result.scalar_one_or_none()
        if not agency:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENCY_NOT_FOUND", "message": "Agence introuvable"}
            )

        agency.is_active = False
        await self.db.commit()
