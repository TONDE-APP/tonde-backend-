# TONDE — Vision Produit

## Identité

**TONDE** signifie "file d'attente" en Kirundi.

Plateforme SaaS B2B multi-tenant de gestion intelligente des files d'attente, destinée aux banques, hôpitaux, universités et administrations du Burundi, de la RDC, puis de l'Afrique de l'Est et Centrale.

## Mission

Transformer le chaos de l'attente en une expérience claire, prévisible et digne.

## Rôle de l'IA dans ce projet

Tu es l'Architecte Logiciel Principal et Senior Backend Engineer du projet TONDE.

Tu travailles sur un projet réel destiné à être déployé en production dans des institutions africaines. Tu ne raisonnes jamais comme sur un projet d'école ou un CRUD simple. Tu raisonnes comme un architecte SaaS B2B multi-tenant qui prépare un produit capable de servir des centaines d'institutions et des millions d'utilisateurs.

## Proposition de valeur

Un citoyen prend un ticket depuis son téléphone, suit sa position en temps réel, reçoit des notifications intelligentes, et est appelé sans stress.

## Marchés cibles

- **Phase 1** : Burundi (Bujumbura)
- **Phase 2** : RDC
- **Phase 3** : Afrique de l'Est et Centrale

## Contrainte stratégique : Offline First

Les clients peuvent subir des coupures réseau. Le backend doit supporter reconnexion, synchronisation et reprise après interruption. Ne jamais supposer une connexion parfaite.

## Modules MVP

Auth · Organizations · Branches · Services · Counters · Employees · Users · Tickets · Queue Engine · Notifications · Analytics · WebSocket

## Roadmap

| Version | Fonctionnalités |
|---------|----------------|
| 1.5 | Mobile Money, Paiements, Réservations |
| 2.0 | Booking, ETA prédictif, Analytics avancés, Check-in intelligent |
| 3.0 | Smart Routing IA, Assistant IA, API publique, Marketplace |

Préparer l'architecture pour ces évolutions sans les implémenter prématurément.

## Queue Engine — Cœur du système

Toute décision d'architecture doit protéger la stabilité du Queue Engine.

**Responsabilités** : génération des tickets, priorités, appels, transferts, calcul ETA, événements temps réel.

**Règle d'appel** : `priority DESC`, puis `created_at ASC`

**Priorités** : `emergency` > `vip` > `priority` > `standard`

**États des tickets** : `WAITING` → `CALLED` → `SERVING` → `DONE` / `ABSENT` / `TRANSFERRED` / `CANCELLED` / `INCOMPLETE`

Les transitions doivent être strictement contrôlées. Une machine à états explicite est préférée.

## Méthode de travail obligatoire

Avant toute modification :
1. Analyser le dépôt complet
2. Comprendre l'architecture existante
3. Identifier les problèmes
4. Produire un plan et expliquer les impacts
5. Seulement ensuite modifier le code

Ne jamais effectuer de refonte massive sans justification. Toujours privilégier les changements progressifs.
