"""
Schémas Pydantic v2 pour les tickets.
Séparés des modèles SQLAlchemy — ce sont les contrats de l'API.
"""
from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional


class CreateTicketRequest(BaseModel):
    agency_id: str
    service_id: str
    # Valeurs acceptées : standard, priority, vip, emergency
    priority: str = "standard"

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        allowed = {"standard", "priority", "vip", "emergency"}
        if v not in allowed:
            raise ValueError(f"Priorité invalide. Valeurs acceptées : {', '.join(allowed)}")
        return v


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    number: str                              # Ex: "B-145"
    status: str                              # waiting, called, serving, done...
    priority: str                            # standard, priority, vip, emergency
    agency_id: str
    service_id: str
    qr_token: str                            # Pour le QR Code affiché sur le mobile
    position: int                            # Position actuelle dans la file
    total_in_queue: int                      # Nombre total de tickets devant
    estimated_wait_minutes: Optional[int] = None
    created_at: datetime
    counter_name: Optional[str] = None       # Guichet assigné si appelé


class TicketHistoryResponse(BaseModel):
    """Réponse paginée pour l'historique des tickets."""
    model_config = ConfigDict(from_attributes=True)

    items: list[TicketResponse]
    total: int          # Nombre total de tickets (toutes pages)
    page: int           # Page actuelle
    page_size: int      # Taille de la page
    has_next: bool      # true si une page suivante existe


class QueueUpdateEvent(BaseModel):
    """Structure des messages WebSocket envoyés au client mobile."""
    type: str                     # "queue_update", "your_turn", "absent_warning"
    ticket_id: str
    ticket_number: str
    current_number: str           # Numéro actuellement servi dans la salle
    position: int
    total_in_queue: int
    estimated_wait_minutes: int
    counter_name: Optional[str] = None


class CallNextRequest(BaseModel):
    """Requête du guichetier pour appeler le prochain ticket."""
    agency_id: str
    service_id: str   # File à cibler — chaque service a sa propre file Redis
    counter_id: str
    counter_name: str
