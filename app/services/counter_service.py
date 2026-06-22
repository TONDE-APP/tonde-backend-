"""
CounterService — Logique métier pour la gestion des guichets.

Règle de sécurité absolue : toute opération filtre par org_id.
Un admin ne peut voir et modifier que les guichets de son organisation.

Pattern : Router → Service → Model
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException

from app.models.counter import Counter
from app.models.agency import Agency
from app.schemas.counter import (
    CreateCounterRequest,
    UpdateCounterRequest,
    CounterResponse,
    CounterListResponse,
)


class CounterService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _verify_agency_belongs_to_org(
        self, agency_id: str, org_id: str
    ) -> Agency:
        """
        Vérifie que l'agence existe et appartient à l'organisation.

        Raises:
            HTTPException 404: Si l'agence n'existe pas ou n'appartient pas à l'org
        """
        result = await self.db.execute(
            select(Agency).where(
                Agency.id == agency_id,
                Agency.org_id == org_id,
                Agency.is_active == True,  # noqa: E712
            )
        )
        agency = result.scalar_one_or_none()
        if not agency:
            raise HTTPException(
                status_code=404,
                detail={"code": "AGENCY_NOT_FOUND", "message": "Agence introuvable ou inactive"}
            )
        return agency

    async def create(
        self, org_id: str, agency_id: str, data: CreateCounterRequest
    ) -> CounterResponse:
        """
        Crée un nouveau guichet dans une agence.

        Args:
            org_id: ID de l'organisation (isolation multi-tenant)
            agency_id: ID de l'agence où créer le guichet
            data: Données de création (name, description)

        Returns:
            CounterResponse avec le guichet créé

        Raises:
            HTTPException 404: Si l'agence n'existe pas dans l'org
            HTTPException 409: Si un guichet avec ce nom existe déjà dans l'agence
        """
        await self._verify_agency_belongs_to_org(agency_id, org_id)

        # Vérifier unicité du nom dans l'agence
        existing = await self.db.execute(
            select(Counter).where(
                Counter.agency_id == agency_id,
                Counter.name == data.name.strip(),
                Counter.is_active == True,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "COUNTER_NAME_TAKEN",
                    "message": f"Un guichet nommé '{data.name}' existe déjà dans cette agence",
                }
            )

        counter = Counter(
            org_id=org_id,
            agency_id=agency_id,
            **data.model_dump(),
        )
        self.db.add(counter)
        await self.db.commit()
        await self.db.refresh(counter)
        return CounterResponse.model_validate(counter)

    async def get_by_id(
        self, counter_id: str, org_id: str
    ) -> CounterResponse:
        """
        Récupère un guichet par son ID.

        Args:
            counter_id: UUID du guichet
            org_id: org_id de l'appelant (isolation multi-tenant)

        Returns:
            CounterResponse

        Raises:
            HTTPException 404: Si le guichet n'existe pas dans l'org
        """
        result = await self.db.execute(
            select(Counter).where(
                Counter.id == counter_id,
                Counter.org_id == org_id,
            )
        )
        counter = result.scalar_one_or_none()
        if not counter:
            raise HTTPException(
                status_code=404,
                detail={"code": "COUNTER_NOT_FOUND", "message": "Guichet introuvable"}
            )
        return CounterResponse.model_validate(counter)

    async def list(
        self,
        org_id: str,
        agency_id: str,
        page: int = 1,
        page_size: int = 20,
        active_only: bool = False,
    ) -> CounterListResponse:
        """
        Liste les guichets d'une agence avec pagination.

        Args:
            org_id: Isolation multi-tenant obligatoire
            agency_id: Filtrer par agence
            page: Numéro de page
            page_size: Éléments par page (max 100)
            active_only: Si True, retourne uniquement les guichets actifs

        Returns:
            CounterListResponse avec items et métadonnées de pagination
        """
        await self._verify_agency_belongs_to_org(agency_id, org_id)

        page_size = min(page_size, 100)
        offset = (page - 1) * page_size

        query = select(Counter).where(
            Counter.org_id == org_id,
            Counter.agency_id == agency_id,
        )
        count_query = select(func.count(Counter.id)).where(
            Counter.org_id == org_id,
            Counter.agency_id == agency_id,
        )

        if active_only:
            query = query.where(Counter.is_active == True)  # noqa: E712
            count_query = count_query.where(Counter.is_active == True)  # noqa: E712

        query = query.order_by(Counter.created_at.asc()).offset(offset).limit(page_size)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        counters = result.scalars().all()

        return CounterListResponse(
            items=[CounterResponse.model_validate(c) for c in counters],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update(
        self, counter_id: str, org_id: str, data: UpdateCounterRequest
    ) -> CounterResponse:
        """
        Met à jour un guichet existant.

        Args:
            counter_id: UUID du guichet à modifier
            org_id: org_id de l'appelant (isolation multi-tenant)
            data: Champs à mettre à jour

        Returns:
            CounterResponse mis à jour

        Raises:
            HTTPException 404: Si le guichet n'existe pas dans l'org
        """
        result = await self.db.execute(
            select(Counter).where(
                Counter.id == counter_id,
                Counter.org_id == org_id,
            )
        )
        counter = result.scalar_one_or_none()
        if not counter:
            raise HTTPException(
                status_code=404,
                detail={"code": "COUNTER_NOT_FOUND", "message": "Guichet introuvable"}
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(counter, field, value)

        await self.db.commit()
        await self.db.refresh(counter)
        return CounterResponse.model_validate(counter)

    async def open(self, counter_id: str, org_id: str) -> CounterResponse:
        """
        Ouvre un guichet pour recevoir des clients.

        Transition : is_open = False → True

        Args:
            counter_id: UUID du guichet
            org_id: Isolation multi-tenant

        Returns:
            CounterResponse mis à jour

        Raises:
            HTTPException 400: Si le guichet est déjà ouvert
            HTTPException 404: Si le guichet n'existe pas
        """
        result = await self.db.execute(
            select(Counter).where(
                Counter.id == counter_id,
                Counter.org_id == org_id,
                Counter.is_active == True,  # noqa: E712
            )
        )
        counter = result.scalar_one_or_none()
        if not counter:
            raise HTTPException(
                status_code=404,
                detail={"code": "COUNTER_NOT_FOUND", "message": "Guichet introuvable"}
            )
        if counter.is_open:
            raise HTTPException(
                status_code=400,
                detail={"code": "COUNTER_ALREADY_OPEN", "message": "Ce guichet est déjà ouvert"}
            )

        counter.is_open = True
        await self.db.commit()
        await self.db.refresh(counter)
        return CounterResponse.model_validate(counter)

    async def close(self, counter_id: str, org_id: str) -> CounterResponse:
        """
        Ferme un guichet — plus de tickets appelés depuis ce guichet.

        Transition : is_open = True → False

        Args:
            counter_id: UUID du guichet
            org_id: Isolation multi-tenant

        Returns:
            CounterResponse mis à jour

        Raises:
            HTTPException 400: Si le guichet est déjà fermé
            HTTPException 404: Si le guichet n'existe pas
        """
        result = await self.db.execute(
            select(Counter).where(
                Counter.id == counter_id,
                Counter.org_id == org_id,
            )
        )
        counter = result.scalar_one_or_none()
        if not counter:
            raise HTTPException(
                status_code=404,
                detail={"code": "COUNTER_NOT_FOUND", "message": "Guichet introuvable"}
            )
        if not counter.is_open:
            raise HTTPException(
                status_code=400,
                detail={"code": "COUNTER_ALREADY_CLOSED", "message": "Ce guichet est déjà fermé"}
            )

        counter.is_open = False
        counter.current_ticket_id = None
        await self.db.commit()
        await self.db.refresh(counter)
        return CounterResponse.model_validate(counter)

    async def delete(self, counter_id: str, org_id: str) -> None:
        """
        Désactive un guichet (soft delete).

        Args:
            counter_id: UUID du guichet
            org_id: Isolation multi-tenant

        Raises:
            HTTPException 404: Si le guichet n'existe pas dans l'org
        """
        result = await self.db.execute(
            select(Counter).where(
                Counter.id == counter_id,
                Counter.org_id == org_id,
            )
        )
        counter = result.scalar_one_or_none()
        if not counter:
            raise HTTPException(
                status_code=404,
                detail={"code": "COUNTER_NOT_FOUND", "message": "Guichet introuvable"}
            )

        counter.is_open = False
        counter.is_active = False
        await self.db.commit()
