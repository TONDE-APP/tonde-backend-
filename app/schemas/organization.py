"""
Schémas Pydantic v2 pour le module Organizations.
"""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator, EmailStr


# ── Secteurs autorisés ────────────────────────────────────────────────────────
OrgSector = Literal["bank", "hospital", "university", "administration", "other"]


# ── Requêtes ──────────────────────────────────────────────────────────────────
class CreateOrganizationRequest(BaseModel):
    name: str
    slug: str
    sector: OrgSector
    description: str | None = None
    country: str = "Burundi"
    city: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    website: str | None = None
    logo_url: str | None = None

    @field_validator("slug")
    @classmethod
    def slug_must_be_valid(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Le slug ne peut contenir que des lettres minuscules, chiffres et tirets")
        return v

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le nom ne peut pas être vide")
        return v.strip()


class UpdateOrganizationRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    country: str | None = None
    city: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    website: str | None = None
    logo_url: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Le nom ne peut pas être vide")
        return v.strip() if v else v


# ── Réponses ──────────────────────────────────────────────────────────────────
class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    sector: str
    description: str | None
    country: str
    city: str | None
    phone: str | None
    email: str | None
    website: str | None
    logo_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
    total: int
    page: int
    page_size: int
