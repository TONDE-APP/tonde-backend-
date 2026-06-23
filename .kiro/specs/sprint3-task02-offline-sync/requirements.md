# S3-02 — Offline Sync — Synchronisation Bidirectionnelle

## Contexte

TONDE vise le marché africain où les coupures réseau sont fréquentes. Le backend doit supporter :
- Reconnexion
- Synchronisation
- Reprise après interruption

> **Contrainte stratégique : Offline First**
> Les clients peuvent subir des coupures réseau. Le backend doit supporter reconnexion, synchronisation et reprise après interruption. Ne jamais supposer une connexion parfaite.

## Objectif

Créer les endpoints pour synchroniser les données entre le client mobile et le backend.

## Sources

Sprint 3 dans `.kiro/steering/sprint1.md` :
> **Sprint 3 : Synchronisation et Intégration des Canaux (Jours 71-90)**
> - Endpoints de synchronisation bidirectionnelle pour le mode Offline
> - Intégration des passerelles SMS/USSD locales (Africa's Talking)
> - Finalisation de la suite de tests et validation finale avec Vital

## Scope

### Principe : Optimistic UI + Sync

```
1. Mobile : action locale → UI mise à jour immédiatement
2. Mobile : action envoyée au backend quand connexion disponible
3. Backend : traite la commande ou retourne conflit
4. Mobile : resolve les conflits (last-write-wins ou manuel)
```

### Endpoints à créer

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/v1/sync/state` | État actuel (tickets, positions) |
| POST | `/api/v1/sync/actions` | Envoyer les actions hors-ligne |
| GET | `/api/v1/sync/changes` | Récupérer les changements depuis last_sync |

### Scénarios Offline

#### Scénario 1 : Prise de ticket hors-ligne
```
1. Client n'a pas de réseau
2. Client prend un ticket "local" (UUID généré localement)
3. Réseau revient
4. Client POST /sync/actions avec le ticket
5. Backend : valide et persiste
6. Backend : retourne le ticket avec UUID réel (ou conflit)
```

#### Scénario 2 : Consulta

...

 des changements
```
1. Client se reconnecte
2. Client GET /sync/changes?since=2026-01-01T10:00:00Z
3. Backend : retourne tous les changements depuis cette date
4. Client : met à jour son état local
```

#### Scénario 3 : Conflict resolution
```
1. Client A prend ticket T1 à 10h00
2. Client B prend le même numéro à 10h01 (mais était offline)
3. Client B se reconnecte et sync
4. Backend détecte le conflit
5. Backend : génère un nouveau numéro pour Client B
6. Backend : notifie Client B du changement
```

## Contraintes

1. **Idempotence** : une action syncée 2x ne doit pas créer 2 tickets
2. **Conflict detection** : détecter les conflits de numéros/positions
3. **Conflict resolution** : stratégie last-write-wins avec notification
4. **Sync window** : ne pas sync plus de 7 jours de données
