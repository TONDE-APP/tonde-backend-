# S2-09 — Transfert Ticket

## Contexte

La machine à états du ticket (`app/models/ticket.py`) prévoit l'état `TRANSFERRED` :

```python
TicketStatus.TRANSFERRED = "transferred"  # Transféré vers un autre guichet/service

ALLOWED_TRANSITIONS = {
    TicketStatus.CALLED: [TicketStatus.SERVING, TicketStatus.ABSENT, TicketStatus.TRANSFERRED],
    # ...
    TicketStatus.TRANSFERRED: [],  # Terminal
}
```

Mais il n'existe pas d'endpoint pour effectuer ce transfert.

## Objectif

Permettre à un agent/guichetier de transférer un ticket vers un autre service ou un autre guichet.

## Scope

### Endpoint à créer

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/v1/tickets/{ticket_id}/transfer` | Transférer un ticket |

### Flux de transfert

```
1. Agent appelle un ticket (CALLED)
2. Client se présente mais a besoin d'un autre service
3. Agent clique "Transférer" et sélectionne le nouveau service
4. Backend :
   - Change le statut → TRANSFERRED
   - Retire de l'ancienne file Redis
   - Log dans queue_log (S2-04)
   - Client peut maintenant prendre un nouveau ticket
5. Client doit prendre un nouveau ticket dans le service approprié
```

## Permissions

| Rôle | Peut transférer |
|------|----------------|
| AGENT | Son propre guichet |
| SUPERVISOR | N'importe quel ticket de son agence |
| ADMIN_AGENCY | N'importe quel ticket de son agence |
| ADMIN_ORG | N'importe quel ticket de son org |

## Contraintes

1. Seul un ticket en état `CALLED` peut être transféré
2. Le service cible doit exister dans la même agence
3. Le ticket transféré ne peut plus être rappelé (état terminal)
4. Logger le transfert dans queue_log (S2-04)
