# TONDE — Workflow de l'équipe

> Comment on travaille ensemble chez TONDE.
> Lis ce fichier avant de toucher au code.

---

## L'équipe et les repos

TONDE est composé de plusieurs applications. Chaque développeur travaille sur **son application**, dans **son propre repo**.

| Application | Repo GitHub | Responsable |
|-------------|-------------|-------------|
| Backend API | `tonde-backend-` | Vital |
| Mobile Flutter | `tonde-mobile` | Dev Mobile |
| Web Admin | `tonde-web-admin` | Dev Web |
| Desktop Guichet | `tonde-desktop` | Dev Desktop |

**Chaque repo est indépendant. Tu ne touches pas au repo d'un autre.**

---

## Comment on se coordonne

### Notion
Toutes les tâches du sprint sont dans Notion.
- Vital crée les tâches et les assigne
- Chaque dev vérifie **ses tâches** avant de commencer à coder
- On met à jour le statut : `À faire` → `En cours` → `Terminé`
- **Avant de commencer quelque chose, vérifie Notion. Si ce n'est pas dans Notion, tu ne le fais pas.**

### WhatsApp (groupe équipe)
- Pour les questions rapides
- Pour dire "je commence la tâche X"
- Pour signaler un blocage
- **Jamais de décisions importantes sur WhatsApp — ça va dans Notion**

---

## Comment Vital crée un repo pour un développeur

**Vital fait ça une seule fois par projet :**

```
1. Crée le repo sur GitHub (sous l'organisation TONDE-APP)
2. Configure le ruleset protect-main
3. Invite le développeur (Settings → Collaborators → Add people → rôle Write)
4. Envoie le lien du repo sur WhatsApp
```

Le développeur reçoit l'invitation par email, il accepte, et il peut commencer.

---

## Comment un développeur rejoint son repo (une seule fois)

Quand Vital t'envoie le lien du repo sur WhatsApp :

```bash
# 1. Télécharger le projet sur ton ordinateur
git clone https://github.com/TONDE-APP/NOM-DU-REPO.git
cd NOM-DU-REPO

# 2. Configurer l'environnement
cp .env.example .env
# Ouvrir .env et remplir les valeurs
# (Vital t'envoie les valeurs sur WhatsApp en privé)

# 3. Lancer le projet
docker-compose up -d --build
```

C'est fait. Tu ne refais jamais cette étape.

---

## Comment un développeur travaille au quotidien

### Étape 1 — Vérifier Notion
Regarde ta tâche assignée. Comprends ce que tu dois faire.
Si tu ne comprends pas → message sur WhatsApp à Vital.

### Étape 2 — Récupérer la dernière version

```bash
git checkout main
git pull origin main
```

**Toujours faire ça avant de commencer.** Sinon tu travailles sur une vieille version.

### Étape 3 — Créer ta branche

```bash
git checkout -b feat/nom-de-ta-tache
```

Exemples selon la tâche dans Notion :
```
feat/organizations-endpoints
feat/login-page
fix/ticket-display-bug
```

### Étape 4 — Coder

Fais ta tâche. Teste localement. Vérifie que tout fonctionne.

### Étape 5 — Sauvegarder

```bash
git add .
git commit -m "feat: description de ce que tu as fait"
```

### Étape 6 — Envoyer sur GitHub

```bash
git push -u origin feat/nom-de-ta-tache
```

### Étape 7 — Ouvrir un Pull Request

1. Va sur GitHub, ouvre le repo
2. Clique le bouton vert **"Compare & pull request"**
3. Écris ce que tu as fait
4. Clique **"Create pull request"**
5. **Envoie le lien du PR sur WhatsApp au groupe**

### Étape 8 — Attendre l'approbation de Vital

Vital review ton code. Il peut :
- ✅ Approuver → il merge → ta tâche est terminée
- 💬 Commenter → tu corriges → tu repousses → il re-review

### Étape 9 — Mettre à jour Notion

Change le statut de ta tâche à `Terminé`.

---

## Règles importantes

**✅ Ce qu'on fait toujours**
- On vérifie Notion avant de commencer
- On dit sur WhatsApp ce sur quoi on travaille
- On crée une branche pour chaque tâche
- On ouvre un PR et on envoie le lien sur WhatsApp
- On met à jour Notion quand c'est terminé

**❌ Ce qu'on ne fait jamais**
- Pousser directement sur `main` — c'est bloqué de toute façon
- Commencer une tâche qui n'est pas dans Notion
- Travailler sur le repo d'un autre développeur
- Garder le silence quand on est bloqué depuis plus de 30 minutes

---

## En cas de conflit Git

Si Git te dit qu'il y a un conflit quand tu fais `git pull` :
1. **Ne panique pas**
2. Message immédiat sur WhatsApp au groupe
3. Vital ou un coéquipier t'aide à résoudre

---

## Résumé en une phrase

> **Notion dit quoi faire. WhatsApp pour communiquer. GitHub pour le code. Vital approuve tout ce qui va sur main.**
