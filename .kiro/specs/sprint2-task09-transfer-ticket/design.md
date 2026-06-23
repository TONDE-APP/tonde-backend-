# S2-09 — Design Technique

## Architecture

```
app/
├── schemas/
│   └── ticket.py                 # Ajouter TransferTicketRequest
├── services/
│   └── ticket_service.py        # Ajouter transfer_ticket()
└── routers/
    └── tickets.py                # Ajouter POST /transfer
```

## Schéma de la requête

### POST /api/v1/tickets/{ticket_id}/transfer

**Auth :** Bearer token (rôle ≥ AGENT)
**Body :**
```json
{
    "target_service_id": "uuid",
    "reason": "Le client a besoin du service Crédit"
}
```

**Response 200 :**
```json
{
    "success": true,
    "message": "Ticket transféré",
    "ticket": {
        "id": "uuid",
        "number": "A-42",
        "status": "transferred"
    }
}
```

**Errors :**
- 400 : Ticket pas en état CALLED
- 404 : Service cible inexistant
- 403 : Pas le droit de transférer ce ticket

## Logique métier

```python
async def transfer_ticket(self, ticket_id: str, target_service_id: str, 
                          reason: str, user_id: str) -> dict:
    # 1. Vérifier que le ticket est en état CALLED
    # 2. Vérifier que le service cible existe dans la même agence
    # 3. Transition vers TRANSFERRED (via _transition)
    # 4. Retirer de l'ancienne file Redis
    # 5. Logger dans queue_log (S2-04)
    # 6. Commit
```

## Points à traiter

1. **Vérifier état CALLED** : utiliser la machine à états existante
2. **Même agence** : le service cible doit être dans la même agence que le ticket actuel
3. **Queue Logs** : dépend de S2-04 pour l'audit trail
4. **Notification** : informer le client que son ticket a été transféré (WebSocket)
