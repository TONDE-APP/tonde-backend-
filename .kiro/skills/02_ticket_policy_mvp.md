# TONDE - Politique Officielle des Tickets MVP

Version : MVP v1.0

## Principe Fondamental

Un utilisateur ne peut posséder qu'un seul ticket actif à la fois.

Cette règle est obligatoire pour :

* éviter les abus
* éviter la réservation massive
* préserver l'équité

---

## Définition d'un Ticket Actif

Sont considérés comme actifs :

* WAITING
* CALLED
* SERVING
* ABSENT
* TRANSFERRED
* INCOMPLETE

---

## Définition d'un Ticket Terminé

Ne sont plus actifs :

* DONE
* CANCELLED

---

## Règle Backend

Avant toute création de ticket :

Le Queue Engine doit vérifier :

Existe-t-il déjà un ticket actif pour cet utilisateur ?

Si OUI :

Retour erreur :

409 CONFLICT

Message :

"Vous possédez déjà un ticket actif."

---

## Exemple

Utilisateur :

Jean

Organisation :

BANCOBU

Ticket :

B-047

Statut :

WAITING

Tentative :

Créer un second ticket

Résultat :

REFUSÉ

---

## Cas Autorisé

Ticket BANCOBU :

DONE

Nouvelle demande :

CHUK

Résultat :

AUTORISÉ

Le client peut maintenant obtenir un nouveau ticket.

---

## Objectif

Une personne = un ticket actif maximum.
