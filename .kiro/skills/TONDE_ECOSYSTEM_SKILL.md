---
name: tonde-ecosystem
description: "Utilise ce skill en PREMIER, avant tout autre skill TONDE, pour toute tâche sur le projet. Ce skill est le manifeste de cohésion de l'écosystème TONDE. Il doit être lu par chaque agent IA travaillant sur n'importe quelle couche du projet (backend, mobile, web-admin, desktop). Il définit comment les 4 applications s'articulent autour d'un seul backend FastAPI, comment un agent doit signaler à Vital qu'il a besoin d'une interface d'une autre couche, et quelles règles de synchronisation s'appliquent à l'ensemble du système. Déclenche ce skill dès qu'une tâche touche à une intégration entre deux couches, à un contrat d'API, à un événement WebSocket partagé, à un schéma de données multi-tenant, ou à la coordination entre équipes."
license: Propriété exclusive du projet TONDE — Chef de projet : Vital.
---

# TONDE — Manifeste d'Intégration Écosystème

*Version 2.0 — Juin 2026 — Document de Cohésion Technique pour Tous les Agents IA du Projet*

---

## 1. CE QUE TOUT AGENT IA DOIT SAVOIR AVANT DE COMMENCER

**TONDE est un grand système. Tu n'en travailles qu'une partie.**

Que tu travailles sur le Backend, le Mobile, le Web Admin ou le Desktop Guichet, tu dois avoir conscience que les trois autres couches existent, sont développées en parallèle, et dépendent toutes du même cœur backend FastAPI.

Ta responsabilité est double :
1. **Respecter scrupuleusement** les contrats d'interface de la couche qui t'a été assignée.
2. **Signaler explicitement à Vital** dès que tu as besoin d'une interface, d'un endpoint, d'un événement ou d'une structure de données qui appartient à une autre couche.

**Tu ne dois jamais inventer, supposer ou simuler le comportement d'une autre couche.** Si tu en as besoin, tu le dis.

---

## 2. LA CARTE DU GRAND SYSTÈME TONDE

```
                    ┌─────────────────────────────────────┐
                    │         BACKEND FASAPI (Python)      │
                    │   Logique Métier · Queue Engine      │
                    │   PostgreSQL · Redis · WebSocket     │
                    │   SKILL : tonde-backend              │
                    └──────────────┬──────────────────────┘
                                   │
                   ┌───────────────┼───────────────┐
                   │               │               │
          ┌────────▼──────┐ ┌──────▼──────┐ ┌────▼──────────┐
          │  MOBILE       │ │  WEB ADMIN  │ │  DESKTOP      │
          │  Flutter      │ │  React/Vite │ │  Tauri/Rust   │
          │               │ │             │ │               │
          │  Citoyens &   │ │  Admins &   │ │  Agents de    │
          │  Clients      │ │  Superviseurs│ │  Guichet      │
          │               │ │             │ │               │
          │  SKILL :      │ │  SKILL :    │ │  SKILL :      │
          │  tonde-mobile │ │  tonde-web- │ │  tonde-desktop│
          │               │ │  admin      │ │               │
          └───────────────┘ └─────────────┘ └───────────────┘
```

**Chaque frontend parle uniquement au backend.** Les frontends ne communiquent pas directement entre eux — c'est le backend qui orchestre tout.

---

## 3. QUI FAIT QUOI : RESPONSABILITÉS PAR COUCHE

### Backend FastAPI (`tonde-backend`)
Centralise toute la logique métier et la persistance. C'est la **seule source de vérité** du système.
- Gère l'authentification JWT + OTP
- Fait tourner le Queue Engine Redis (ZSET)
- Expose les endpoints REST et les canaux WebSocket
- Applique le cloisonnement multi-tenant (`org_id`)
- Émet tous les événements standardisés

### Mobile Flutter (`tonde-mobile`)
Interface des citoyens et clients finaux.
- Permet de prendre un ticket, suivre sa position, recevoir des notifications FCM
- Consomme l'API REST du backend pour toutes les opérations
- Maintient une connexion WebSocket légère pour les mises à jour de file en temps réel
- Fonctionne en mode Offline-First avec cache Hive

### Web Admin React/Vite (`tonde-web-admin`)
Outil de pilotage pour les administrateurs et superviseurs.
- Configure les organisations, agences, services et guichets
- Affiche les Live Counters et les KPIs en temps réel via WebSocket
- Gère les rôles utilisateurs et les permissions RBAC
- Produit des rapports et exports PDF/Excel

### Desktop Guichet Tauri/Rust (`tonde-desktop`)
Outil de combat pour les agents de guichet.
- Pilote le Queue Engine via des commandes ultra-rapides
- Gère le cycle de vie complet d'un ticket (Appel, Absent, Transfert, Clôture)
- Maintient une connexion WebSocket native en Rust indépendante de l'UI
- Fonctionne en mode Offline-First avec SQLite embarqué

---

## 4. RÈGLE FONDAMENTALE : COMMENT SIGNALER UN BESOIN INTER-COUCHES

**Quand tu travailles sur ta couche et que tu as besoin de quelque chose d'une autre couche, tu NE dois PAS :**
- Inventer un endpoint qui n'existe peut-être pas encore
- Supposer la structure d'un payload d'une autre couche
- Simuler le comportement du backend ou d'un autre frontend
- Bloquer ton travail en silence

**Tu DOIS :**

Signaler le besoin à Vital de manière explicite et structurée, selon ce format :

```
🔗 DÉPENDANCE INTER-COUCHE DÉTECTÉE

Couche concernée  : [ex: Backend FastAPI]
Besoin identifié  : [ex: Un endpoint POST /api/v1/tickets/{id}/transfer]
Payload attendu   : [ex: { "target_service_id": "uuid", "reason": "string" }]
Réponse attendue  : [ex: { "success": true, "data": { ticket mis à jour } }]
Impact sur mon travail : [ex: Sans cet endpoint, je ne peux pas implémenter
                          le bouton [T] de transfert de ticket dans le Desktop]
Action demandée   : Valide ce contrat ou fournis-moi le schéma existant.
```

Ce signalement permet à Vital de coordonner avec l'agent responsable de l'autre couche, ou de te fournir directement la documentation nécessaire. **Tu peux continuer à travailler sur d'autres parties de ta couche en attendant la réponse.**

---

## 5. LES CONTRATS D'INTERFACE PARTAGÉS

### 5.1 Authentification — Commune à tous les frontends

Toute requête authentifiée vers le backend doit inclure :

```http
Authorization: Bearer <JWT_ACCESS_TOKEN>
```

Le token JWT contient implicitement :
- `user_id` — identifiant unique de l'utilisateur
- `org_id` — identifiant du tenant (institution)
- `role` — niveau d'accès (`CLIENT`, `AGENT`, `SUPERVISEUR`, `ADMIN_AGENCE`, `ADMIN_ORG`, `SUPER_ADMIN`)

**Règle absolue :** Ne jamais stocker ni forger l'`org_id` côté client. Il est extrait du token JWT par le backend.

### 5.2 Format de Réponse API — Uniforme sur tous les endpoints

**Succès :**
```json
{
  "success": true,
  "data": { ... },
  "message": "Opération réussie"
}
```

**Erreur :**
```json
{
  "success": false,
  "detail": {
    "code": "NOM_ERREUR_METIER",
    "message": "Description lisible de l'erreur"
  }
}
```

### 5.3 Hiérarchie des Données — Identique dans tous les frontends

La structure de données suit toujours cette hiérarchie. Ne jamais créer d'entité en dehors de cette arborescence :

```
Organization  →  Branch/Agency  →  Service  →  Counter  →  Ticket
```

Chaque entité possède un `org_id` UUID pour le cloisonnement multi-tenant.

---

## 6. DICTIONNAIRE DES ÉVÉNEMENTS WEBSOCKET PARTAGÉS

Ces événements sont émis par le backend et peuvent être reçus par un ou plusieurs frontends. **Les noms d'événements sont immuables.** Si tu as besoin d'un événement qui n'existe pas dans cette liste, tu le signales à Vital selon le protocole de la section 4.

| Événement | Émetteur | Récepteurs | Description |
|---|---|---|---|
| `TICKET_CREATED` | Backend | Web Admin, Mobile | Un nouveau ticket vient d'être créé dans la file |
| `TICKET_CALLED` | Backend | Mobile, Desktop, Web Admin | Un ticket est appelé à un guichet précis |
| `QUEUE_UPDATE` | Backend | Mobile, Web Admin | Recalcul des positions et ETAs de la file |
| `TICKET_ABSENT` | Backend | Web Admin | Un client ne s'est pas présenté |
| `TICKET_TRANSFERRED` | Backend | Mobile, Web Admin | Un ticket a été redirigé vers un autre service |
| `GUICHET_STATUS` | Backend | Web Admin | Un guichet change d'état (Ouvert / Pause / Fermé) |
| `AGENT_PAUSE` | Backend | Web Admin | Un agent a mis son guichet en pause |
| `BROADCAST_MESSAGE` | Backend | Tous | Message d'information générale diffusé à tous |

---

## 7. ENVIRONNEMENTS — CONFIGURATION CENTRALISÉE

Toutes les couches utilisent les mêmes URLs de backend selon l'environnement. Ces valeurs ne sont jamais écrites en dur dans le code.

| Environnement | URL Backend REST | URL WebSocket |
|---|---|---|
| `development` | `http://localhost:8000` (Android: `10.0.2.2:8000`) | `ws://localhost:8000/ws` |
| `staging` | `https://api-staging.tonde.app` | `wss://api-staging.tonde.app/ws` |
| `production` | `https://api.tonde.app` | `wss://api.tonde.app/ws` |

**OTP de développement universel :** `123456` — Valide uniquement en environnement `development`.

---

## 8. RÈGLES DE SYNCHRONISATION OFFLINE (OUTBOX PATTERN)

Les couches Mobile (Hive/Isar) et Desktop (SQLite) fonctionnent en mode Offline-First. Pour éviter les conflits lors de la resynchronisation, le cache local doit **fidèlement refléter la structure relationnelle du backend** :

- Les IDs locaux sont des UUID v4 identiques à ceux que le backend assignerait
- Les statuts de tickets respectent la machine à états officielle du backend : `WAITING → CALLED → SERVING → DONE / ABSENT / INCOMPLETE`
- Les actions effectuées hors-ligne sont enregistrées dans une file d'attente locale (Outbox) et rejouées dans l'ordre chronologique à la reconnexion
- En cas de conflit, la règle est : **le backend a toujours raison**

---

## 9. CE QU'AUCUN AGENT IA NE DOIT JAMAIS FAIRE

* `❌` **Inventer un endpoint ou un schéma de données sans le signaler à Vital.**
* `❌` **Dupliquer de la logique métier (calcul d'ETA, machine à états du ticket) dans un frontend — cette logique appartient exclusivement au backend.**
* `❌` **Créer des événements WebSocket personnalisés non répertoriés dans le dictionnaire officiel (section 6).**
* `❌` **Assumer que l'`org_id` peut être stocké ou manipulé librement côté client.**
* `❌` **Commencer à implémenter une fonctionnalité qui dépend d'une autre couche sans avoir d'abord signalé le besoin à Vital et obtenu le contrat d'interface.**

---

## 10. RÉSUMÉ OPÉRATIONNEL POUR CHAQUE AGENT IA

```
AVANT DE CODER :
  1. Lis le skill de ta couche (tonde-backend / tonde-mobile / tonde-web-admin / tonde-desktop)
  2. Lis ce manifeste pour comprendre les dépendances du grand système
  3. Identifie si ta tâche nécessite une interface d'une autre couche

PENDANT LE DÉVELOPPEMENT :
  4. Respecte les contrats d'interface définis dans ce document
  5. Si tu as besoin de quelque chose d'une autre couche → signale-le à Vital (section 4)
  6. Continue à travailler sur les autres parties de ta couche en attendant la réponse

AVANT DE SOUMETTRE :
  7. Vérifie que ton code ne duplique pas de logique métier qui appartient au backend
  8. Vérifie que tous les événements WebSocket utilisés sont dans le dictionnaire officiel
  9. Vérifie que l'org_id est bien propagé via le token JWT et non stocké en clair
```

---

*TONDE Ecosystem Integration Manifest — Document de Référence Racine pour tous les Agents IA.*
*Propriété exclusive du projet TONDE — Chef de projet : Vital.*
