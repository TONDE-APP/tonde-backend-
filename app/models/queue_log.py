"""
Modèle QueueLog — Table 'queue_logs' dans PostgreSQL.

Audit trail de chaque transition d'état d'un ticket.
Chaque changement de statut génère une ligne immuable dans cette table.

Utilité :
  - Audit trail complet (qui a fait quoi, quand)
  - Source de données pour le pipeline Analytics (S2-06)
  - Calcul des métriques temps réel (DÉCISION 9) :
      * Temps d'attente réel par agence/service/heure
      * Temps de traitement par agent
      * Pics horaires
      * Taux d'absence (ABSENT / total CALLED)
      * Performances guichet

Règle : ces lignes ne sont jamais modifiées ni supprimées.
Elles constituent la source de vérité historique du système.
"""
import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Enum as SAEnum, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class QueueLogAction(str, enum.Enum):
    """
    Actions loggées dans la table queue_logs.
    Correspond directement aux transitions de la machine à états du ticket.
    """
    TICKET_CREATED    = "ticket_created"    # Nouveau ticket créé → WAITING
    TICKET_CALLED     = "ticket_called"     # WAITING → CALLED (guichetier appelle)
    TICKET_SERVING    = "ticket_serving"    # CALLED → SERVING (client présent)
    TICKET_DONE       = "ticket_done"       # SERVING → DONE (service terminé)
    TICKET_ABSENT     = "ticket_absent"     # CALLED → ABSENT (timeout)
    TICKET_RETURNED   = "ticket_returned"   # ABSENT → WAITING (client revient)
    TICKET_TRANSFERRED = "ticket_transferred"  # CALLED → TRANSFERRED
    TICKET_CANCELLED  = "ticket_cancelled"  # WAITING → CANCELLED (client annule)
    TICKET_INCOMPLETE = "ticket_incomplete" # SERVING → INCOMPLETE (service interrompu)


class QueueLog(Base):
    """
    Enregistrement immuable d'une action sur un ticket.

    Une ligne = une transition d'état.
    Le ticket peut avoir autant de lignes que de transitions dans sa vie.

    Exemple pour un ticket normal :
      1. TICKET_CREATED   | waiting    | -          | t=0
      2. TICKET_CALLED    | called     | counter_id | t=15min
      3. TICKET_SERVING   | serving    | counter_id | t=16min
      4. TICKET_DONE      | done       | counter_id | t=21min
    """
    __tablename__ = "queue_logs"

    # ── Identifiant unique ────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Multi-tenant obligatoire ──────────────────────────────
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )

    # ── Ticket concerné ───────────────────────────────────────
    ticket_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        index=True,
    )

    # ── Contexte métier ───────────────────────────────────────
    agency_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        index=True,
    )
    service_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("services.id", ondelete="CASCADE"),
        index=True,
    )

    # ── Action et transitions ─────────────────────────────────
    action: Mapped[QueueLogAction] = mapped_column(
        SAEnum(QueueLogAction),
        index=True,
    )
    # État du ticket AVANT la transition
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # État du ticket APRÈS la transition
    to_status: Mapped[str] = mapped_column(String(20))

    # ── Acteur de l'action ────────────────────────────────────
    # L'utilisateur qui a déclenché l'action (agent, client, système)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Rôle de l'acteur au moment de l'action (pour analytics par rôle)
    actor_role: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # ── Guichet impliqué ──────────────────────────────────────
    # Renseigné pour les actions CALLED, SERVING, DONE, ABSENT
    counter_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    counter_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Métriques de temps ────────────────────────────────────
    # Durée en secondes depuis la création du ticket jusqu'à cette action
    # Permet de calculer le temps d'attente réel à chaque étape
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Données additionnelles ────────────────────────────────
    # JSON libre pour des métadonnées spécifiques à l'action
    # Ex: {"reason": "...", "target_service_id": "..."} pour un transfert
    extra_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Horodatage de l'action ────────────────────────────────
    # Indexé pour les requêtes analytiques par plage de temps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<QueueLog {self.action} | ticket={self.ticket_id} "
            f"| {self.from_status} → {self.to_status}>"
        )
