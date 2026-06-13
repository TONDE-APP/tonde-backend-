# Guide de contribution — TONDE Backend

> Ce document explique comment travailler en équipe sur le projet TONDE.
> Lis-le entièrement avant de toucher au code.

---

## 1. Récupérer le projet (une seule fois)

```bash
git clone https://github.com/TONDE-APP/tonde-backend-.git
cd tonde-backend-
cp .env.example .env
# Remplis le .env avec tes valeurs
docker-compose up -d --build
```

---

## 2. Avant de commencer à travailler

**Toujours partir de la version la plus récente.**

```bash
git checkout main
git pull origin main
```

---

## 3. Créer ta branche de travail

Ne jamais travailler directement sur `main`.

```bash
git checkout -b feat/nom-de-ce-que-tu-fais
```

**Conventions de nommage :**

| Préfixe | Quand l'utiliser |
|---------|-----------------|
| `feat/` | Nouvelle fonctionnalité |
| `fix/` | Correction d'un bug |
| `chore/` | Configuration, dépendances |
| `docs/` | Documentation |

Exemples :
```
feat/organizations-module
feat/counter-endpoints
fix/ticket-status-transition
docs/update-readme
```

---

## 4. Coder et tester

Fais ton travail. Avant de pousser, vérifie que les tests passent :

```bash
docker-compose exec api pytest --tb=short -q
```

---

## 5. Sauvegarder et pousser

```bash
git add .
git commit -m "feat: description claire de ce que tu as fait"
git push -u origin feat/nom-de-ta-branche
```

---

## 6. Ouvrir un Pull Request

1. Va sur `https://github.com/TONDE-APP/tonde-backend-`
2. Clique le bouton vert **"Compare & pull request"**
3. Remplis le titre et la description
4. Coche toutes les cases de la checklist
5. Clique **"Create pull request"**

**Vital reçoit une notification, review ton code, et approuve ou commente.**

Tu ne peux pas merger toi-même. C'est voulu.

---

## 7. Après approbation et merge

```bash
git checkout main
git pull origin main
git branch -d feat/nom-de-ta-branche
```

---

## Règle d'or

> **On ne pousse jamais directement sur `main`.
> On crée une branche → on travaille → on ouvre un PR → on attend l'approbation de Vital.**
