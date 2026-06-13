# TONDE Backend

> **TONDE** signifie *"file d'attente"* en Kirundi.

Plateforme SaaS B2B multi-tenant de gestion intelligente des files d'attente, conçue pour les banques, hôpitaux, universités et administrations du Burundi, de la RDC et de l'Afrique de l'Est.

**Mission :** Transformer le chaos de l'attente en une expérience claire, prévisible et digne.

---

## Stack technique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| Framework | FastAPI | 0.111.0 |
| Runtime | Python | 3.12+ |
| Base de données | PostgreSQL | 15 |
| Cache / File | Redis | 7 |
| ORM | SQLAlchemy async | 2.0.30 |
| Migrations | Alembic | 1.13.1 |
| Validation | Pydantic v2 | 2.7.1 |
| Auth | JWT + OTP SMS | — |
| Temps réel | WebSocket + Redis Pub/Sub | — |
| Conteneurisation | Docker + Docker Compose | — |

---

## Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et démarré
- [Git](https://git-scm.com/)
- Python 3.12+ (optionnel, pour développement hors Docker)

---

## Installation & démarrage rapide

```bash
# 1. Cloner le projet
git clone https://github.com/TONDE-APP/tonde-backend-.git
cd tonde-backend-

# 2. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos valeurs

# 3. Lancer l'environnement complet
docker-compose up -d --build

# 4. Appliquer les migrations
docker-compose exec api alembic upgrade head

# 5. Vérifier que l'API est vivante
# Swagger  : http://localhost:8000/docs
# Health   : http://localhost:8000/health
# Redis UI : http://localhost:8081
```

---

## Structure du projet

```
tonde-backend/
├── app/
│   ├── main.py              # Point d'entrée FastAPI
│   ├── core/                # Config, DB, Redis, Sécurité, Dépendances
│   ├── models/              # Modèles SQLAlchemy (tables PostgreSQL)
│   ├── schemas/             # Schémas Pydantic v2 (validation I/O)
│   ├── services/            # Logique métier
│   ├── routers/             # Endpoints HTTP et WebSocket
│   └── websocket/           # Gestionnaire WebSocket + événements
├── migrations/              # Migrations Alembic
├── tests/                   # Tests pytest
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### Hiérarchie des données

```
Organization → Branch/Agency → Service → Counter → Ticket
```

Chaque entité possède un `org_id` pour le cloisonnement multi-tenant strict.

---

## Commandes utiles

```bash
# Lancer les tests
docker-compose exec api pytest --tb=short -q

# Créer une migration après modification d'un modèle
docker-compose exec api alembic revision --autogenerate -m "description"

# Appliquer les migrations
docker-compose exec api alembic upgrade head

# Voir les logs de l'API en temps réel
docker-compose logs -f api

# Redémarrer l'API après modification
docker-compose restart api

# Arrêter tous les conteneurs
docker-compose down
```

---

## Variables d'environnement

Copier `.env.example` → `.env` et remplir les valeurs.

| Variable | Description | Exemple |
|----------|-------------|---------|
| `DATABASE_URL` | URL PostgreSQL async | `postgresql+asyncpg://...` |
| `REDIS_URL` | URL Redis | `redis://localhost:6379` |
| `JWT_SECRET_KEY` | Clé secrète JWT | `openssl rand -hex 32` |
| `ENVIRONMENT` | Environnement | `development` / `production` |
| `AFRICAS_TALKING_API_KEY` | Clé SMS Africa's Talking | — |

> ⚠️ Ne jamais committer le fichier `.env`. Il est dans `.gitignore`.

---

## Architecture temps réel

```
Queue Engine (service)
      ↓ publie événement
Redis Pub/Sub
      ↓ listener background
WebSocket Manager
      ↓ diffuse
Clients (mobile Flutter, desktop Tauri)
```

### Événements WebSocket officiels

| Événement | Description |
|-----------|-------------|
| `TICKET_CALLED` | Un numéro est appelé au guichet |
| `QUEUE_UPDATE` | Mise à jour position / ETA |
| `TICKET_ABSENT` | Client non-présent après timeout |
| `TICKET_TRANSFERRED` | Ticket transféré vers un autre service |
| `GUICHET_STATUS` | Guichet ouvert / fermé / pause |
| `BROADCAST_MESSAGE` | Message général salle d'attente |

---

## États des tickets

```
WAITING → CALLED → SERVING → DONE
                ↘ ABSENT  → WAITING (retour file)
                ↘ TRANSFERRED
         ↘ CANCELLED
                   SERVING → INCOMPLETE
```

---

## Workflow de contribution

Ce projet utilise un workflow **Pull Request obligatoire**. Aucun push direct sur `main`.

```bash
# 1. Partir de main à jour
git checkout main && git pull origin main

# 2. Créer une branche
git checkout -b feat/nom-de-la-feature

# 3. Développer, tester
docker-compose exec api pytest --tb=short -q

# 4. Committer
git add .
git commit -m "feat: description claire"

# 5. Pousser et ouvrir un Pull Request
git push -u origin feat/nom-de-la-feature
```

Conventions de nommage des branches :
- `feat/` — nouvelle fonctionnalité
- `fix/` — correction de bug
- `chore/` — configuration, dépendances
- `docs/` — documentation

---

## Environnements

| Environnement | URL API |
|---------------|---------|
| Local | `http://localhost:8000` |
| Mobile (émulateur Android) | `http://10.0.2.2:8000` |
| Staging | `https://api-staging.tonde.app` |
| Production | `https://api.tonde.app` |

---

## Écosystème TONDE

| Repo | Description | Stack |
|------|-------------|-------|
| `tonde-backend` | API REST + WebSocket | FastAPI + PostgreSQL + Redis |
| `tonde-mobile` | App citoyens | Flutter |
| `tonde-web-admin` | Dashboard admins & superviseurs | React + Vite |
| `tonde-desktop` | Interface guichetiers | Tauri + Rust |

---

## Roadmap

| Version | Fonctionnalités |
|---------|----------------|
| **v1.0 (MVP)** | Auth, Organizations, Queue Engine, WebSocket |
| v1.5 | Mobile Money, Paiements, Réservations |
| v2.0 | ETA prédictif, Analytics avancés |
| v3.0 | Smart Routing IA, API publique |

---

## Licence

Propriété exclusive du projet TONDE.
Chef de projet : **Vital** — Burundi 🇧🇮

---

*Construire l'infrastructure de service de demain pour l'Afrique.*
