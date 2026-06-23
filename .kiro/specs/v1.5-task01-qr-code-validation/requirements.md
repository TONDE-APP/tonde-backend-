# V1.5-01 — QR Code Validation

## Contexte

Chaque ticket possède un `qr_token` unique (généré dans le modèle Ticket). Ce token permet :
- Au client de retrouver son ticket rapidement
- À l'agent de scanner le QR code pour appeler le ticket
- Au client de vérifier son tour

## Objectif

Créer l'endpoint pour valider et récupérer les informations d'un ticket via QR code.

## Scope

### Endpoint à créer

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/v1/tickets/qr/{qr_token}` | Valider QR code et retourner ticket |

### Cas d'usage

#### Cas 1 : Agent scanne QR pour appeler
```
1. Agent scanne le QR code du client
2. Backend retourne les infos du ticket
3. Agent peut confirmer "_called" ou "serving"
```

#### Cas 2 : Client scanne son propre ticket
```
1. Client scanne son propre QR code
2. Backend retourne position actuelle, ETA, statut
3. Client sait où il en est
```

#### Cas 3 : Client scanne pour rejoindre une file
```
1. Client scanne un QR code d'agence
2. Backend retourne les services disponibles
3. Client choisit un service et prend ticket
```

## Contraintes

1. Le QR token doit être lié à un ticket valide
2. Ticket expiré (> 24h) → erreur 404
3. Pas d'authentification requise (scan public)
4. Retourner uniquement les infos non sensibles
