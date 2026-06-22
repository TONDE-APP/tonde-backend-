# Requirements Document

## Introduction

TASK-03 corrige la règle de contrôle d'unicité des tickets actifs dans le Queue Engine de TONDE.
Actuellement, `_get_active_ticket()` filtre par `agency_id`, ce qui permet à un utilisateur de détenir
simultanément un ticket à la BANCOBU et un ticket au CHUK. Ce comportement est interdit selon la
DÉCISION 1 des décisions d'architecture validées par Vital.

Ce correctif étend la portée de la vérification au niveau de la **plateforme entière** (toutes agences,
toutes organisations confondues pour un même `user_id`), étend la liste des statuts considérés comme
"actifs", et enrichit la réponse HTTP 409 pour permettre au mobile de rediriger l'utilisateur vers son
ticket en cours.

## Glossary

- **TicketService** : Service métier Python (`app/services/ticket_service.py`) responsable de la
  création, du suivi et des transitions d'état des tickets.
- **Ticket** : Entité SQLAlchemy représentant une prise en charge d'un utilisateur dans une agence
  pour un service donné.
- **TicketStatus** : Enum Python listant tous les états possibles d'un ticket
  (`WAITING`, `CALLED`, `SERVING`, `DONE`, `ABSENT`, `TRANSFERRED`, `CANCELLED`, `INCOMPLETE`).
- **ACTIVE_STATUSES** : Constante liste des statuts considérés comme "en cours" bloquant toute
  nouvelle création de ticket pour le même utilisateur.
- **Statut terminal** : Statut depuis lequel aucune transition n'est possible (`DONE`, `CANCELLED`,
  `INCOMPLETE`, `TRANSFERRED`). Un ticket en statut terminal libère l'utilisateur.
- **HTTP 409** : Code de réponse HTTP "Conflict" retourné quand l'utilisateur tente de créer un
  second ticket actif.
- **active_ticket_id** : Champ UUID inclus dans la réponse 409 permettant au client mobile de
  naviguer directement vers le ticket actif existant.
- **active_ticket_number** : Champ lisible (ex : `A-12`) inclus dans la réponse 409 pour afficher
  un message d'erreur humainement compréhensible.
- **org_id** : Identifiant d'organisation assurant l'isolation multi-tenant. Présent sur chaque
  entité métier.

---

## Requirements

### Requirement 1 — Vérification globale du ticket actif

**User Story :** En tant qu'utilisateur mobile, je veux être empêché de prendre un second ticket
tant que mon ticket actuel n'est pas terminé, quelle que soit l'agence où il se trouve, afin d'éviter
les incohérences et de garantir un accès équitable aux services.

#### Acceptance Criteria

1. WHEN un utilisateur tente de créer un ticket, THE TicketService SHALL vérifier l'existence d'un
   ticket actif pour cet utilisateur sur **toute la plateforme** (sans filtre sur `agency_id`).

2. WHEN un utilisateur possède un ticket dont le statut est `WAITING`, `CALLED`, `SERVING`, `ABSENT`,
   `TRANSFERRED` ou `INCOMPLETE`, THE TicketService SHALL refuser la création d'un nouveau ticket
   avec HTTP 409.

3. WHEN un utilisateur possède un ticket dont le statut est `DONE` ou `CANCELLED`, THE TicketService
   SHALL autoriser la création d'un nouveau ticket.

4. IF un ticket actif est trouvé lors de la tentative de création, THEN THE TicketService SHALL
   retourner une réponse HTTP 409 avec le corps JSON contenant les champs `code`,
   `message`, `active_ticket_id` et `active_ticket_number`.

5. THE TicketService SHALL définir la constante `ACTIVE_STATUSES` regroupant exactement les statuts
   `WAITING`, `CALLED`, `SERVING`, `ABSENT`, `TRANSFERRED` et `INCOMPLETE`.

---

### Requirement 2 — Signature de `_get_active_ticket()` sans filtre agence

**User Story :** En tant que développeur backend, je veux que la méthode `_get_active_ticket()`
interroge la base de données sans contrainte sur `agency_id`, afin d'appliquer correctement la règle
globale d'unicité.

#### Acceptance Criteria

1. THE TicketService SHALL supprimer le paramètre `agency_id` de la signature de `_get_active_ticket()`.

2. WHEN `_get_active_ticket()` est appelée avec un `user_id`, THE TicketService SHALL exécuter une
   requête SQLAlchemy filtrant uniquement sur `Ticket.user_id == user_id` et
   `Ticket.status.in_(ACTIVE_STATUSES)`.

3. THE TicketService SHALL mettre à jour tous les appels internes à `_get_active_ticket()` pour
   qu'ils ne transmettent plus `agency_id`.

4. WHEN `_get_active_ticket()` ne trouve aucun ticket actif, THE TicketService SHALL retourner `None`.

5. WHEN `_get_active_ticket()` trouve un ticket actif, THE TicketService SHALL retourner l'objet
   `Ticket` correspondant.

---

### Requirement 3 — Réponse HTTP 409 enrichie

**User Story :** En tant que client mobile Flutter, je veux recevoir l'identifiant et le numéro du
ticket actif dans la réponse d'erreur 409, afin de pouvoir rediriger automatiquement l'utilisateur
vers l'écran de suivi de son ticket existant.

#### Acceptance Criteria

1. WHEN la création d'un ticket est refusée pour cause de ticket actif existant, THE TicketService
   SHALL retourner une `HTTPException` avec `status_code=409` et `detail` structuré en dict Python.

2. THE TicketService SHALL inclure dans le `detail` de la 409 le champ `code` avec la valeur
   `"TICKET_ALREADY_ACTIVE"`.

3. THE TicketService SHALL inclure dans le `detail` de la 409 le champ `message` contenant le
   numéro du ticket actif et son statut courant, sous la forme :
   `"Vous avez déjà un ticket actif (<number> — statut : <status>). Attendez qu'il soit terminé ou annulez-le."`.

4. THE TicketService SHALL inclure dans le `detail` de la 409 le champ `active_ticket_id` contenant
   l'UUID string du ticket actif existant.

5. THE TicketService SHALL inclure dans le `detail` de la 409 le champ `active_ticket_number`
   contenant le numéro lisible du ticket actif (ex : `"A-12"`).

---

### Requirement 4 — Cohérence avec `return_to_queue()`

**User Story :** En tant que guichetier, je veux que lorsqu'un ticket absent revient en file
(`ABSENT → WAITING`), ce ticket soit toujours considéré comme actif, afin qu'un utilisateur ne puisse
pas profiter d'un retour en file pour créer un second ticket simultanément.

#### Acceptance Criteria

1. WHILE un ticket a le statut `ABSENT`, THE TicketService SHALL considérer ce ticket comme actif
   et bloquer toute nouvelle création de ticket pour le même utilisateur.

2. WHEN `return_to_queue()` remet un ticket de `ABSENT` à `WAITING`, THE TicketService SHALL
   maintenir ce ticket dans la liste des tickets actifs bloquants.

3. WHILE un ticket a le statut `TRANSFERRED` ou `INCOMPLETE`, THE TicketService SHALL considérer
   ce ticket comme actif et bloquer toute nouvelle création de ticket pour le même utilisateur.

---

### Requirement 5 — Condition de libération

**User Story :** En tant qu'utilisateur, je veux pouvoir prendre un nouveau ticket dès que mon
ticket précédent est marqué `DONE` ou `CANCELLED`, afin de ne pas être bloqué inutilement après
avoir été servi ou avoir annulé.

#### Acceptance Criteria

1. WHEN un ticket passe en statut `DONE`, THE TicketService SHALL permettre à l'utilisateur de
   créer un nouveau ticket immédiatement.

2. WHEN un ticket passe en statut `CANCELLED`, THE TicketService SHALL permettre à l'utilisateur
   de créer un nouveau ticket immédiatement.

3. THE TicketService SHALL ne considérer comme bloquants que les tickets dont le statut fait
   partie de `ACTIVE_STATUSES`, et jamais les tickets `DONE` ou `CANCELLED`.
