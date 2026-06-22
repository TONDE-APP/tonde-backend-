"""
EmployeeService — Logique métier pour la gestion des employés.

Un Employee est le lien entre un User et une Organisation.
Il définit le rôle opérationnel de l'utilisateur (agent, superviseur, admin).

Règle de sécurité absolue : toute opération filtre par org_id.

Pattern : Router → Service → Model
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException

from app.models.employee import Employee, EmployeeStatus
from app.models.user import User, UserRole
from app.schemas.employee import (
    CreateEmployeeRequest,
    UpdateEmployeeRequest,
    EmployeeResponse,
    EmployeeListResponse,
)


class EmployeeService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _verify_user_exists(self, user_id: str) -> User:
        """
        Vérifie que l'utilisateur existe et est actif.

        Raises:
            HTTPException 404: Si l'utilisateur n'existe pas
        """
        result = await self.db.execute(
            select(User).where(
                User.id == user_id,
                User.is_active == True,  # noqa: E712
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=404,
                detail={"code": "USER_NOT_FOUND", "message": "Utilisateur introuvable ou inactif"}
            )
        return user

    async def create(
        self, org_id: str, data: CreateEmployeeRequest
    ) -> EmployeeResponse:
        """
        Crée un employé en liant un User existant à une organisation.

        Args:
            org_id: ID de l'organisation (isolation multi-tenant)
            data: user_id, role, agency_id (optionnel), counter_id (optionnel)

        Returns:
            EmployeeResponse avec l'employé créé

        Raises:
            HTTPException 404: Si l'utilisateur n'existe pas
            HTTPException 409: Si l'utilisateur est déjà employé dans cette org
        """
        await self._verify_user_exists(data.user_id)

        # Vérifier qu'il n'est pas déjà employé dans cette org
        existing = await self.db.execute(
            select(Employee).where(
                Employee.user_id == data.user_id,
                Employee.org_id == org_id,
                Employee.status != EmployeeStatus.INACTIVE,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "EMPLOYEE_EXISTS",
                    "message": "Cet utilisateur est déjà enregistré comme employé dans cette organisation",
                }
            )

        employee = Employee(
            org_id=org_id,
            **data.model_dump(),
        )
        self.db.add(employee)

        # Mettre à jour le rôle du User pour refléter son nouveau rôle
        user_result = await self.db.execute(
            select(User).where(User.id == data.user_id)
        )
        user = user_result.scalar_one()
        user.role = data.role
        user.org_id = org_id

        await self.db.commit()
        await self.db.refresh(employee)
        return EmployeeResponse.model_validate(employee)

    async def get_by_id(
        self, employee_id: str, org_id: str
    ) -> EmployeeResponse:
        """
        Récupère un employé par son ID.

        Args:
            employee_id: UUID de l'employé
            org_id: Isolation multi-tenant

        Returns:
            EmployeeResponse

        Raises:
            HTTPException 404: Si l'employé n'existe pas dans l'org
        """
        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.org_id == org_id,
            )
        )
        employee = result.scalar_one_or_none()
        if not employee:
            raise HTTPException(
                status_code=404,
                detail={"code": "EMPLOYEE_NOT_FOUND", "message": "Employé introuvable"}
            )
        return EmployeeResponse.model_validate(employee)

    async def list(
        self,
        org_id: str,
        agency_id: str | None = None,
        role: UserRole | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> EmployeeListResponse:
        """
        Liste les employés d'une organisation avec filtres optionnels.

        Args:
            org_id: Isolation multi-tenant obligatoire
            agency_id: Filtrer par agence (optionnel)
            role: Filtrer par rôle (optionnel)
            page: Numéro de page
            page_size: Éléments par page (max 100)

        Returns:
            EmployeeListResponse avec items et métadonnées de pagination
        """
        page_size = min(page_size, 100)
        offset = (page - 1) * page_size

        query = select(Employee).where(Employee.org_id == org_id)
        count_query = select(func.count(Employee.id)).where(Employee.org_id == org_id)

        if agency_id:
            query = query.where(Employee.agency_id == agency_id)
            count_query = count_query.where(Employee.agency_id == agency_id)

        if role:
            query = query.where(Employee.role == role)
            count_query = count_query.where(Employee.role == role)

        # Exclure les inactifs par défaut
        query = query.where(Employee.status != EmployeeStatus.INACTIVE)
        count_query = count_query.where(Employee.status != EmployeeStatus.INACTIVE)

        query = query.order_by(Employee.created_at.desc()).offset(offset).limit(page_size)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        employees = result.scalars().all()

        return EmployeeListResponse(
            items=[EmployeeResponse.model_validate(e) for e in employees],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update(
        self, employee_id: str, org_id: str, data: UpdateEmployeeRequest
    ) -> EmployeeResponse:
        """
        Met à jour le rôle, l'affectation ou le statut d'un employé.

        Args:
            employee_id: UUID de l'employé
            org_id: Isolation multi-tenant
            data: Champs à mettre à jour

        Returns:
            EmployeeResponse mis à jour

        Raises:
            HTTPException 404: Si l'employé n'existe pas dans l'org
        """
        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.org_id == org_id,
            )
        )
        employee = result.scalar_one_or_none()
        if not employee:
            raise HTTPException(
                status_code=404,
                detail={"code": "EMPLOYEE_NOT_FOUND", "message": "Employé introuvable"}
            )

        update_data = data.model_dump(exclude_unset=True)

        # Si le rôle change, mettre à jour aussi le User
        if "role" in update_data:
            user_result = await self.db.execute(
                select(User).where(User.id == employee.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                user.role = update_data["role"]

        for field, value in update_data.items():
            setattr(employee, field, value)

        await self.db.commit()
        await self.db.refresh(employee)
        return EmployeeResponse.model_validate(employee)

    async def deactivate(self, employee_id: str, org_id: str) -> None:
        """
        Désactive un employé (soft delete).
        Remet le User au rôle CLIENT.

        Args:
            employee_id: UUID de l'employé
            org_id: Isolation multi-tenant

        Raises:
            HTTPException 404: Si l'employé n'existe pas dans l'org
        """
        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.org_id == org_id,
            )
        )
        employee = result.scalar_one_or_none()
        if not employee:
            raise HTTPException(
                status_code=404,
                detail={"code": "EMPLOYEE_NOT_FOUND", "message": "Employé introuvable"}
            )

        employee.status = EmployeeStatus.INACTIVE

        # Remettre le User au rôle CLIENT
        user_result = await self.db.execute(
            select(User).where(User.id == employee.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            user.role = UserRole.CLIENT
            user.org_id = None

        await self.db.commit()
