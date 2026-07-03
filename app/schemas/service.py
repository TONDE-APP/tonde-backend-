"""
Schémas Pydantic v2 pour le module Services.

Un service est proposé par une agence (ex: Dépôt, Retrait, Consultation).
Chaque service possède son propre préfixe de ticket et sa propre file Redis.
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


# ── Requêtes ──────────────────────────────────────────────────────────────────
class CreateServiceRequest(BaseModel):
    name: str
    description: str | None = None
    ticket_prefix: str = "A"
    avg_duration_minutes: int = 5

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le nom du service ne peut pas être vide")
        return v.strip()

    @field_validator("ticket_prefix")
    @classmethod
    def prefix_must_be_valid(cls, v: str) -> str:
        v = v.strip().upper()
        if not v or len(v) > 5 or not v.isalpha():
            raise ValueError("Le préfixe doit contenir 1 à 5 lettres (ex: A, B, VIP)")
        return v

    @field_validator("avg_duration_minutes")
    @classmethod
    def duration_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("La durée moyenne doit être d'au moins 1 minute")
        return v


class UpdateServiceRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    ticket_prefix: str | None = None
    avg_duration_minutes: int | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Le nom du service ne peut pas être vide")
        return v.strip() if v else v

    @field_validator("ticket_prefix")
    @classmethod
    def prefix_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip().upper()
            if not v or len(v) > 5 or not v.isalpha():
                raise ValueError("Le préfixe doit contenir 1 à 5 lettres (ex: A, B, VIP)")
        return v

    @field_validator("avg_duration_minutes")
    @classmethod
    def duration_must_be_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("La durée moyenne doit être d'au moins 1 minute")
        return v


# ── Réponses ──────────────────────────────────────────────────────────────────
class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str | None
    agency_id: str
    name: str
    description: str | None
    ticket_prefix: str
    avg_duration_minutes: int
    is_active: bool
    created_at: datetime


class ServiceListResponse(BaseModel):
    items: list[ServiceResponse]
    total: int
    page: int
    page_size: int
