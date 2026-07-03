"""
ServiceService — Logique métier pour la gestion des services d'agence.

Un service est une file dédiée au sein d'une agence
(ex: Caisse, Crédit, Conseiller, Consultation).
Chaque service possède son propre préfixe de ticket et
sa propre file Redis (clé segmentée par service_id).

Règle de sécurité absolue : toutes les opérations admin
filtrent par org_id et agency_id.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException

from app.models.agency import Service, Agency
from app.schemas.service import (
    CreateServiceRequest,
    UpdateServiceRequest,
    ServiceResponse,
    ServiceListResponse,
)

logger = logging.getLogger(__name__)


class ServiceService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _verify_agency_belongs_to_org(self, agency_id: str, org_id: str) -> Agency:
        """
        Vérifie que l'agence existe et appartient bien à l'organisation.

        Args:
            agency_id: UUID de l'agence
            org_id: UUID de l'organisation attendue

        Returns:
            L'objet Agency vérifié

        Raises:
            HTTPException 404: Si l'agence n'existe pas dans cet org
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
                detail={
                    "code": "AGENCY_NOT_FOUND",
                    "message": "Agence introuvable ou inactive dans cette organisation",
                },
            )
        return agency

    async def create(
        self,
        org_id: str,
        agency_id: str,
        data: CreateServiceRequest,
    ) -> ServiceResponse:
        """
        Crée un nouveau service dans une agence.

        Vérifie l'unicité du préfixe de ticket au sein de la même agence
        pour éviter les collisions de numérotation (ex: deux services avec 'A').

        Args:
            org_id: ID de l'organisation (isolation multi-tenant)
            agency_id: ID de l'agence cible
            data: Données du service à créer

        Returns:
            ServiceResponse avec le service créé

        Raises:
            HTTPException 404: Agence introuvable dans cet org
            HTTPException 409: Préfixe déjà utilisé dans cette agence
        """
        await self._verify_agency_belongs_to_org(agency_id, org_id)

        # Vérifier l'unicité du préfixe au sein de l'agence
        existing_prefix = await self.db.execute(
            select(Service).where(
                Service.agency_id == agency_id,
                Service.ticket_prefix == data.ticket_prefix,
                Service.is_active == True,  # noqa: E712
            )
        )
        if existing_prefix.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PREFIX_ALREADY_USED",
                    "message": (
                        f"Le préfixe '{data.ticket_prefix}' est déjà utilisé "
                        f"par un autre service actif dans cette agence."
                    ),
                },
            )

        service = Service(
            org_id=org_id,
            agency_id=agency_id,
            **data.model_dump(),
        )
        self.db.add(service)
        await self.db.commit()
        await self.db.refresh(service)

        logger.info(
            f"Service créé: '{service.name}' [prefix={service.ticket_prefix}] "
            f"| agency={agency_id} | org={org_id}"
        )
        return ServiceResponse.model_validate(service)

    async def list_by_agency(
        self,
        agency_id: str,
        page: int = 1,
        page_size: int = 50,
        active_only: bool = True,
    ) -> ServiceListResponse:
        """
        Liste les services d'une agence avec pagination.
        Accessible publiquement par les clients mobiles — pas de filtre org_id ici.

        Args:
            agency_id: UUID de l'agence
            page: Numéro de page (commence à 1)
            page_size: Éléments par page (max 100)
            active_only: Si True, retourne uniquement les services actifs (défaut True)

        Returns:
            ServiceListResponse avec items et métadonnées de pagination
        """
        page_size = min(page_size, 100)
        offset = (page - 1) * page_size

        query = select(Service).where(Service.agency_id == agency_id)
        count_query = select(func.count(Service.id)).where(Service.agency_id == agency_id)

        if active_only:
            query = query.where(Service.is_active == True)  # noqa: E712
            count_query = count_query.where(Service.is_active == True)  # noqa: E712

        query = query.order_by(Service.ticket_prefix.asc()).offset(offset).limit(page_size)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        services = result.scalars().all()

        return ServiceListResponse(
            items=[ServiceResponse.model_validate(s) for s in services],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_by_id(
        self, service_id: str, agency_id: str
    ) -> ServiceResponse:
        """
        Récupère un service par son ID dans une agence.

        Args:
            service_id: UUID du service
            agency_id: UUID de l'agence parente (vérification d'appartenance)

        Returns:
            ServiceResponse

        Raises:
            HTTPException 404: Si le service n'existe pas dans cette agence
        """
        result = await self.db.execute(
            select(Service).where(
                Service.id == service_id,
                Service.agency_id == agency_id,
            )
        )
        service = result.scalar_one_or_none()
        if not service:
            raise HTTPException(
                status_code=404,
                detail={"code": "SERVICE_NOT_FOUND", "message": "Service introuvable"},
            )
        return ServiceResponse.model_validate(service)

    async def update(
        self,
        service_id: str,
        agency_id: str,
        org_id: str,
        data: UpdateServiceRequest,
    ) -> ServiceResponse:
        """
        Met à jour un service existant (mise à jour partielle).

        Si le préfixe est modifié, vérifie que le nouveau préfixe
        n'est pas déjà utilisé par un autre service actif de la même agence.

        Args:
            service_id: UUID du service à modifier
            agency_id: UUID de l'agence parente
            org_id: UUID de l'organisation (isolation multi-tenant)
            data: Champs à mettre à jour

        Returns:
            ServiceResponse mis à jour

        Raises:
            HTTPException 404: Service introuvable
            HTTPException 409: Nouveau préfixe déjà utilisé
        """
        result = await self.db.execute(
            select(Service).where(
                Service.id == service_id,
                Service.agency_id == agency_id,
                Service.org_id == org_id,
            )
        )
        service = result.scalar_one_or_none()
        if not service:
            raise HTTPException(
                status_code=404,
                detail={"code": "SERVICE_NOT_FOUND", "message": "Service introuvable"},
            )

        update_data = data.model_dump(exclude_unset=True)

        # Vérifier l'unicité du nouveau préfixe si modifié
        new_prefix = update_data.get("ticket_prefix")
        if new_prefix and new_prefix != service.ticket_prefix:
            conflict = await self.db.execute(
                select(Service).where(
                    Service.agency_id == agency_id,
                    Service.ticket_prefix == new_prefix,
                    Service.id != service_id,
                    Service.is_active == True,  # noqa: E712
                )
            )
            if conflict.scalar_one_or_none():
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "PREFIX_ALREADY_USED",
                        "message": (
                            f"Le préfixe '{new_prefix}' est déjà utilisé "
                            f"par un autre service actif dans cette agence."
                        ),
                    },
                )

        for field, value in update_data.items():
            setattr(service, field, value)

        await self.db.commit()
        await self.db.refresh(service)

        logger.info(f"Service mis à jour: {service_id} | org={org_id}")
        return ServiceResponse.model_validate(service)

    async def delete(
        self, service_id: str, agency_id: str, org_id: str
    ) -> None:
        """
        Désactive un service (soft delete — is_active=False).

        Un service désactivé n'apparaît plus dans la liste publique
        et ne peut plus recevoir de nouveaux tickets.
        Les tickets existants ne sont pas affectés.

        Args:
            service_id: UUID du service à désactiver
            agency_id: UUID de l'agence parente
            org_id: UUID de l'organisation (isolation multi-tenant)

        Raises:
            HTTPException 404: Service introuvable
        """
        result = await self.db.execute(
            select(Service).where(
                Service.id == service_id,
                Service.agency_id == agency_id,
                Service.org_id == org_id,
            )
        )
        service = result.scalar_one_or_none()
        if not service:
            raise HTTPException(
                status_code=404,
                detail={"code": "SERVICE_NOT_FOUND", "message": "Service introuvable"},
            )

        service.is_active = False
        await self.db.commit()
        logger.info(f"Service désactivé: {service_id} | org={org_id}")
