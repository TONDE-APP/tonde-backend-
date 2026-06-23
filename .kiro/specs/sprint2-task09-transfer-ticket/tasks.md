# S2-09 — Tasks

## Tâches d'implémentation

### 1. Ajouter le Schema
**Fichier :** `app/schemas/ticket.py`

```python
class TransferTicketRequest(BaseModel):
    target_service_id: str
    reason: str | None = None
```

### 2. Ajouter au Service
**Fichier :** `app/services/ticket_service.py`

```python
async def transfer_ticket(
    self,
    ticket_id: str,
    user_id: str,
    org_id: str,
    target_service_id: str,
    reason: str | None = None
) -> dict:
    """
    Transfère un ticket vers un autre service.
    
    Transition : CALLED → TRANSFERRED (terminal)
    """
    # 1. Vérifier le ticket existe et est en état CALLED
    ticket = await self._get_ticket_by_id(ticket_id, org_id)
    if ticket.status != TicketStatus.CALLED:
        raise HTTPException(400, " Seul un ticket CALLED peut être transféré")
    
    # 2. Vérifier le service cible existe dans la même agence
    target_service = await self._get_service(
        target_service_id, ticket.agency_id, org_id
    )
    
    # 3. Transition vers TRANSFERRED
    await self._transition(ticket, TicketStatus.TRANSFERRED)
    
    # 4. Retirer de la file Redis
    await remove_from_queue(org_id, ticket.agency_id, ticket.service_id, ticket.id)
    
    # 5. Logger dans queue_log (si S2-04 fait)
    # await self._log_action(ticket, "TRANSFERRED", user_id, reason)
    
    # 6. Commit
    ticket.transferred_to_service_id = target_service_id
    await self.db.commit()
    
    return {
        "success": True,
        "message": "Ticket transféré",
        "ticket_id": ticket.id,
        "status": ticket.status.value
    }
```

### 3. Ajouter au Router
**Fichier :** `app/routers/tickets.py`

```python
@router.post("/{ticket_id}/transfer", summary="Transférer un ticket vers un autre service")
async def transfer_ticket(
    ticket_id: str,
    body: TransferTicketRequest,
    current_user: User = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Transfère le ticket vers un autre service.
    Seul un ticket en état CALLED peut être transféré.
    """
    service = TicketService(db)
    return await service.transfer_ticket(
        ticket_id=ticket_id,
        user_id=current_user.id,
        org_id=current_user.org_id,
        target_service_id=body.target_service_id,
        reason=body.reason
    )
```

## Tests à écrire

```python
test_transfer_ticket_from_called_success
test_transfer_ticket_not_called_fails
test_transfer_to_invalid_service_fails
test_transfer_different_agency_fails
test_transfer_logged_in_queue_log
```

## Checklist PR

- [ ] Schema TransferTicketRequest ajouté
- [ ] Méthode transfer_ticket() dans TicketService
- [ ] Endpoint POST /transfer ajouté
- [ ] Vérification état CALLED
- [ ] Vérification service cible existe
- [ ] Transition vers TRANSFERRED
- [ ] Retrait de la file Redis
- [ ] Tests passent
