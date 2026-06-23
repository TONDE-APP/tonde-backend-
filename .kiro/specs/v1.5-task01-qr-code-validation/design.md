# V1.5-01 — Design Technique

## Types de QR Code

### QR Ticket
Contient : `ticket:{ticket_id}:{qr_token}`

```
Format: https://tonde.app/ticket/abc123?token=xyz789
```

### QR Agence
Contient : `agency:{agency_id}`

```
Format: https://tonde.app/agency/abc123
```

## Endpoint

### GET /api/v1/tickets/qr/{qr_token}

**Auth :** Aucune (public)
**Response 200 :**
```json
{
    "type": "ticket",
    "ticket": {
        "id": "uuid",
        "number": "A-42",
        "status": "waiting",
        "position": 5,
        "eta_minutes": 20,
        "service_name": "Caisse",
        "agency_name": "BANCOBU Centre-Ville",
        "created_at": "2026-01-01T10:00:00Z"
    }
}
```

**Response 200 (QR Agence) :**
```json
{
    "type": "agency",
    "agency": {
        "id": "uuid",
        "name": "BANCOBU Centre-Ville",
        "address": "Avenue du Commerce",
        "services": [
            {"id": "uuid", "name": "Caisse", "avg_wait": 15},
            {"id": "uuid", "name": "Crédit", "avg_wait": 45}
        ]
    }
}
```

**Response 404 :**
```json
{
    "error": "QR_CODE_INVALID",
    "message": "Ce code QR n'est plus valide ou a expiré"
}
```

## Logique

```python
async def validate_qr(qr_token: str) -> QRValidationResponse:
    # 1. Chercher ticket par qr_token
    ticket = await db.execute(
        select(Ticket).where(Ticket.qr_token == qr_token)
    )
    
    # 2. Si trouvé, retourner infos ticket
    if ticket:
        # Vérifier expiration (24h)
        if ticket.created_at < datetime.utcnow() - timedelta(hours=24):
            raise HTTPException(404, "QR expiré")
        return QRValidationResponse(type="ticket", ticket=...)
    
    # 3. Sinon chercher agence par qr_token (alias)
    agency = await db.execute(
        select(Agency).where(Agency.qr_alias == qr_token)
    )
    if agency:
        return QRValidationResponse(type="agency", agency=...)
    
    # 4. Rien trouvé
    raise HTTPException(404, "QR invalide")
```

## Points à traiter

1. **Génération du QR** : utiliser une lib comme `qrcode` ou `python-qrcode`
2. **Alias QR** : optionnel, pour lier une agence à un QR court
3. **Expiration** : tickets > 24h automatiquement expirés
4. **Sécurité** : ne jamais exposer les IDs internes sans nécessité
