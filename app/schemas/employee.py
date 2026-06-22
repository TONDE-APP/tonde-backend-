"""
Schémas Pydantic v2 pour le module Employees (Agents).
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator
from app.models.user import UserRole
from app.models.employee import EmployeeStatus


# ── Requêtes ──────────────────────────────────────────────────────────────────
class CreateEmployeeRequest(BaseModel):
    """Crée un employé en liant un User existant à une organisation."""
    user_id: str
    agency_id: str | None = None
    counter_id: str | None = None
    role: UserRole = UserRole.AGENT

    @field_validator("role")
    @classmethod
    def role_must_be_staff(cls, v: UserRole) -> UserRole:
        """Un CLIENT ne peut pas être employé."""
        if v == UserRole.CLIENT:
            raise ValueError("Un client ne peut pas être enregistré comme employé")
        return v


class UpdateEmployeeRequest(BaseModel):
    """Met à jour le rôle, l'affectation ou le statut d'un employé."""
    agency_id: str | None = None
    counter_id: str | None = None
    role: UserRole | None = None
    status: EmployeeStatus | None = None

    @field_validator("role")
    @classmethod
    def role_must_be_staff(cls, v: UserRole | None) -> UserRole | None:
        if v == UserRole.CLIENT:
            raise ValueError("Un client ne peut pas être enregistré comme employé")
        return v


# ── Réponses ──────────────────────────────────────────────────────────────────
class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    user_id: str
    agency_id: str | None
    counter_id: str | None
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


class EmployeeListResponse(BaseModel):
    items: list[EmployeeResponse]
    total: int
    page: int
    page_size: int
