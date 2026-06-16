"""
Schémas Pydantic v2 pour le module Branches/Agencies.
"""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator, EmailStr


AgencySector = Literal["bank", "hospital", "university", "administration", "other"]


# ── Requêtes ──────────────────────────────────────────────────────────────────
class CreateAgencyRequest(BaseModel):
    name: str
    slug: str
    sector: AgencySector
    description: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    city: str = "Bujumbura"
    country: str = "Burundi"
    latitude: float | None = None
    longitude: float | None = None
    opens_at: str = "08:00"
    closes_at: str = "17:00"
    logo_url: str | None = None
    max_daily_tickets: int = 500
    avg_service_minutes: int = 5

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

    @field_validator("opens_at", "closes_at")
    @classmethod
    def time_format(cls, v: str) -> str:
        import re
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("Format horaire invalide, utiliser HH:MM")
        return v


class UpdateAgencyRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    opens_at: str | None = None
    closes_at: str | None = None
    logo_url: str | None = None
    max_daily_tickets: int | None = None
    avg_service_minutes: int | None = None
    is_active: bool | None = None
    is_open: bool | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Le nom ne peut pas être vide")
        return v.strip() if v else v

    @field_validator("opens_at", "closes_at")
    @classmethod
    def time_format(cls, v: str | None) -> str | None:
        import re
        if v is not None and not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("Format horaire invalide, utiliser HH:MM")
        return v


# ── Réponses ──────────────────────────────────────────────────────────────────
class AgencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str | None
    name: str
    slug: str
    sector: str
    description: str | None
    phone: str | None
    email: str | None
    address: str | None
    city: str
    country: str
    latitude: float | None
    longitude: float | None
    opens_at: str
    closes_at: str
    logo_url: str | None
    max_daily_tickets: int
    avg_service_minutes: int
    is_active: bool
    is_open: bool
    created_at: datetime
    updated_at: datetime


class AgencyListResponse(BaseModel):
    items: list[AgencyResponse]
    total: int
    page: int
    page_size: int
