"""
Schémas Pydantic v2 pour le module Analytics (S2-06).

Ces schémas définissent les réponses de l'API analytics.
Les données viennent de queue_logs (S2-04).
"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


# ── Paramètres de requête ─────────────────────────────────────────────────────
class AnalyticsPeriodParams(BaseModel):
    """Paramètres de période pour les requêtes analytics."""
    date_from: datetime | None = None
    date_to: datetime | None = None

    @field_validator("date_to")
    @classmethod
    def date_to_after_date_from(cls, v: datetime | None, info) -> datetime | None:
        date_from = info.data.get("date_from")
        if v and date_from and v < date_from:
            raise ValueError("date_to doit être postérieure à date_from")
        return v


# ── Réponses ──────────────────────────────────────────────────────────────────
class AgencySummaryResponse(BaseModel):
    """Résumé des métriques clés d'une agence sur une période."""
    model_config = ConfigDict(from_attributes=True)

    org_id: str
    agency_id: str
    period: dict                          # {from, to}
    total_tickets: int                    # Tickets créés sur la période
    avg_wait_minutes: float               # Temps moyen en file (WAITING → CALLED)
    absence_rate_percent: float           # % de clients absents après appel
    total_called: int                     # Total tickets appelés
    total_absent: int                     # Total tickets marqués absent
    tickets_by_status: dict[str, int]     # done/cancelled/incomplete/transferred
    busiest_hour: int | None              # Heure de pointe (0-23)


class ServiceStatsItem(BaseModel):
    """Statistiques d'un service individuel."""
    service_id: str
    total_tickets: int
    avg_wait_minutes: float


class ServiceStatsResponse(BaseModel):
    """Liste des statistiques par service d'une agence."""
    agency_id: str
    period: dict
    services: list[ServiceStatsItem]


class CounterPerformanceItem(BaseModel):
    """Performance d'un guichet individuel."""
    counter_id: str
    counter_name: str
    tickets_done: int


class CounterPerformanceResponse(BaseModel):
    """Liste des performances par guichet d'une agence."""
    agency_id: str
    period: dict
    counters: list[CounterPerformanceItem]


class HourlyDistributionItem(BaseModel):
    """Volume de tickets pour une heure donnée."""
    hour: int       # 0-23
    ticket_count: int


class HourlyDistributionResponse(BaseModel):
    """Distribution horaire du volume de tickets."""
    agency_id: str
    period: dict
    distribution: list[HourlyDistributionItem]  # 24 entrées
