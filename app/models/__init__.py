"""
Import explicite de tous les modèles SQLAlchemy.

Ce fichier garantit que Base.metadata connaît toutes les tables,
que ce soit pour Alembic (migrations) ou create_tables() en dev.

Règle : ajouter ici tout nouveau modèle créé dans ce dossier.
Ordre d'import : respecter les dépendances FK (parent avant enfant).
"""
from app.models.organization import Organization  # noqa: F401
from app.models.user import User, UserRole        # noqa: F401
from app.models.agency import Agency, Service     # noqa: F401
from app.models.counter import Counter            # noqa: F401
from app.models.employee import Employee, EmployeeStatus  # noqa: F401
from app.models.ticket import (                   # noqa: F401
    Ticket,
    TicketStatus,
    TicketPriority,
    PRIORITY_SCORES,
    ALLOWED_TRANSITIONS,
)
