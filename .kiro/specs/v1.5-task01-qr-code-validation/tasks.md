# V1.5-01 — Tasks

## Tâches d'implémentation

### 1. Ajouter les Schemas
**Fichier :** `app/schemas/ticket.py`

```python
class QRValidationResponse(BaseModel):
    type: Literal["ticket", "agency"]
    ticket: TicketQRResponse | None = None
    agency: AgencyQRResponse | None = None

class TicketQRResponse(BaseModel):
    id: str
    number: str
    status: str
    position: int
    eta_minutes: int
    service_name: str
    agency_name: str
    created_at: datetime

class AgencyQRResponse(BaseModel):
    id: str
    name: str
    address: str | None
    services: list[ServiceSummary]
```

### 2. Ajouter au Service
**Fichier :** `app/services/ticket_service.py`

```python
async def validate_qr_code(self, qr_token: str) -> QRValidationResponse:
    """
    Valide un QR code et retourne les informations associées.
    Public — pas d'authentification requise.
    """
    # Chercher ticket
    ticket_result = await self.db.execute(
        select(Ticket).where(Ticket.qr_token == qr_token)
    )
    ticket = ticket_result.scalar_one_or_none()
    
    if ticket:
        # Vérifier expiration (24h)
        if ticket.created_at < datetime.now(timezone.utc) - timedelta(hours=24):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "QR_EXPIRED", "message": "Ce code QR a expiré"}
            )
        
        # Enrichir avec position Redis
        position = await get_queue_position(
            ticket.org_id, ticket.agency_id, ticket.service_id, ticket.id
        )
        
        return QRValidationResponse(
            type="ticket",
            ticket=TicketQRResponse(
                id=ticket.id,
                number=ticket.number,
                status=ticket.status.value,
                position=position,
                eta_minutes=max(0, (position - 1) * 5),  # TODO: utiliser avg_service_minutes
                service_name=ticket.service.name if ticket.service else "",
                agency_name=ticket.agency.name if ticket.agency else "",
                created_at=ticket.created_at
            )
        )
    
    # Chercher agence (si alias QR)
    agency_result = await self.db.execute(
        select(Agency).where(Agency.qr_alias == qr_token)
    )
    agency = agency_result.scalar_one_or_none()
    
    if agency:
        services_result = await self.db.execute(
            select(Service).where(Service.agency_id == agency.id)
        )
        services = services_result.scalars().all()
        
        return QRValidationResponse(
            type="agency",
            agency=AgencyQRResponse(
                id=agency.id,
                name=agency.name,
                address=agency.address,
                services=[
                    ServiceSummary(id=s.id, name=s.name, avg_wait=s.avg_duration_minutes)
                    for s in services if s.is_active
                ]
            )
        )
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "QR_INVALID", "message": "Code QR invalide"}
    )
```

### 3. Ajouter au Router
**Fichier :** `app/routers/tickets.py`

```python
@router.get("/qr/{qr_token}", summary="Valider un QR code")
async def validate_qr_code(
    qr_token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Valide un QR code et retourne les informations associées.
    Accessible publiquement — pas d'authentification requise.
    
    Types de QR supportés :
    - QR Ticket : affiche position, ETA, statut
    - QR Agence : affiche services disponibles
    """
    service = TicketService(db)
    return await service.validate_qr_code(qr_token)
```

### 4. Ajouter qr_alias à Agency (optionnel)
**Migration :**
```bash
alembic revision --autogenerate -m "add_qr_alias_to_agencies"
```

```python
# Dans app/models/agency.py
qr_alias: Mapped[str | None]  # Alias court pour QR (ex: "bancobu-centre")
```

## Tests à écrire

```python
test_validate_qr_ticket_success
test_validate_qr_ticket_expired_404
test_validate_qr_agency_returns_services
test_validate_qr_invalid_404
test_validate_qr_includes_redis_position
```

## Checklist PR

- [ ] Schema QRValidationResponse créé
- [ ] Méthode validate_qr_code() dans TicketService
- [ ] Endpoint GET /qr/{qr_token}
- [ ] Vérification expiration 24h
- [ ] Support QR Ticket
- [ ] Support QR Agence (si qr_alias implémenté)
- [ ] Position Redis intégrée
- [ ] Tests passent
