<img width="1536" height="864" alt="atihmam_logo" src="https://github.com/user-attachments/assets/cc530f7d-bce1-4472-a58e-7e3bf65a276b" />

# 📋 Atihmam ATS — Documentation Complète

> Système de Suivi des Candidatures intelligent, alimenté par l'IA

---

## Table des matières

1. [Présentation générale](#1-présentation-générale)
2. [Architecture technique](#2-architecture-technique)
3. [Fonctionnalités](#3-fonctionnalités)
4. [Stack technologique](#4-stack-technologique)
5. [Structure du projet](#5-structure-du-projet)
6. [Installation et démarrage local](#6-installation-et-démarrage-local)
7. [Variables d'environnement](#7-variables-denvironnement)
8. [API — Endpoints principaux](#8-api--endpoints-principaux)
9. [Système de scoring IA](#9-système-de-scoring-ia)
10. [Pipeline de traitement des CVs](#10-pipeline-de-traitement-des-cvs)
11. [Intégration Google Drive](#11-intégration-google-drive)
12. [Déploiement](#12-déploiement)
13. [Sécurité](#13-sécurité)

---

## 1. Présentation générale

**Atihmam ATS** est une plateforme de recrutement intelligente qui automatise l'analyse des CVs, le classement des candidats et le suivi du pipeline de recrutement.

L'application se décompose en deux parties :

- **Backend** : API REST construite avec FastAPI (Python), déployée sur **Render**
- **Frontend** : Interface React déployée sur **Vercel**

### Ce que fait l'application

- Un recruteur importe un CV (PDF) manuellement ou via Google Drive
- L'IA extrait automatiquement les informations du candidat (nom, email, compétences, expérience, etc.)
- Un score de 0 à 100 est calculé selon plusieurs dimensions (compétences, expérience, complexité des projets, séniorité, etc.)
- Le recruteur suit les candidats dans un pipeline Kanban (Candidature → Screening → Entretien → Offre → Embauché)
- Les analytics permettent d'analyser la qualité globale du pipeline et d'obtenir des recommandations IA

---

## 2. Architecture technique

```
┌─────────────────────────────────────────────────────────┐
│                     FRONTEND (Vercel)                   │
│              React 19 + Vite + Tailwind CSS             │
│         https://atihmam-ats-application.vercel.app      │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / REST
┌──────────────────────────▼──────────────────────────────┐
│                     BACKEND (Render)                    │
│                FastAPI + Python 3.11                    │
│        https://atihmam-ats-application.onrender.com     │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐  │
│  │   Routes    │  │  Services   │  │  Tâches Celery │  │
│  │  /auth      │  │  ai_service │  │  cv_processing │  │
│  │  /candidates│  │  scoring    │  │  drive_sync    │  │
│  │  /jobs      │  │  cv_parser  │  │                │  │
│  │  /analytics │  │  drive      │  │                │  │
│  │  /feedback  │  │             │  │                │  │
│  └─────────────┘  └─────────────┘  └────────────────┘  │
└──────────┬──────────────┬───────────────────┬───────────┘
           │              │                   │
  ┌────────▼───┐  ┌───────▼──────┐  ┌────────▼───────┐
  │  Supabase  │  │  Valkey/     │  │  Google Drive  │
  │ PostgreSQL │  │  Redis       │  │  + Gemini AI   │
  │    Auth    │  │  (Broker     │  │                │
  │   Storage  │  │   Celery)    │  │                │
  └────────────┘  └──────────────┘  └────────────────┘
```
<img width="1382" height="1627" alt="ATS Architecture Atihmam" src="https://github.com/user-attachments/assets/25f494a5-08f6-43e4-9b42-20e2f84d578d" />

---

## 3. Fonctionnalités

### Gestion des candidats
- Import de CVs en PDF (upload manuel ou synchronisation Google Drive)
- Extraction automatique : nom, email, téléphone, poste, compétences, expériences, formations, projets, langues
- Détection automatique des doublons (via hash SHA-256 du fichier)
- Fiche détaillée par candidat avec données structurées

### Scoring IA multi-dimensionnel
- Score global de 0 à 100
- 7 dimensions analysées : correspondance mots-clés, compétences sémantiques, expérience, complexité des projets, formations, certifications, leadership
- Bonus d'écosystème (maîtrise d'une stack complète) et pénalités (projets répétitifs, faible diversité)
- Apprentissage adaptatif : les poids évoluent selon les retours du recruteur (👍 / 👎)

### Pipeline Kanban
- 6 étapes : Candidature → Screening → Entretien → Offre → Embauché → Refusé
- Transitions validées par une machine à états (certains passages interdits)
- Historique de chaque transition enregistré en base

### Analytics
- Statistiques globales du pipeline (total candidats, score moyen, taux de conversion)
- Distribution des scores, nuage de compétences, répartition par statut
- Recommandations intelligentes basées sur le profil des candidats recrutés
- Re-scoring en masse d'un clic

### Gestion des postes
- Création de postes avec titre, description, exigences et secteur d'activité (30 secteurs disponibles)
- Questions de présélection configurables (diplôme minimum, années d'expérience, certifications requises, questions personnalisées)
- Association candidat ↔ poste pour le scoring ciblé

### Authentification
- Inscription / connexion par email et mot de passe (via Supabase Auth)
- JWT avec expiration configurable
- Réinitialisation de mot de passe par email
- Rôles : `admin` et `recruiter`

---

## 4. Stack technologique

### Backend
| Composant | Technologie |
|-----------|-------------|
| Framework web | FastAPI 0.115 |
| Langage | Python 3.11 |
| Base de données | PostgreSQL via Supabase |
| Authentification | Supabase Auth + JWT (python-jose) |
| File d'attente | Celery 5.6 |
| Broker / Cache | Valkey (compatible Redis) |
| Extraction PDF | pdfplumber |
| Similarité sémantique | SentenceTransformers (all-MiniLM-L6-v2) |
| IA générative | Google Gemini (principal) + DeepSeek / Mistral / NVIDIA (fallback) |
| Stockage fichiers | Supabase Storage |
| Drive | Google Drive API v3 |

### Frontend
| Composant | Technologie |
|-----------|-------------|
| Framework | React 19 |
| Build tool | Vite 8 |
| Routing | React Router 7 |
| Data fetching | TanStack Query 5 |
| État global | Zustand 5 |
| HTTP client | Axios |
| Style | Tailwind CSS 4 |
| Notifications | react-hot-toast |
| Icônes | lucide-react |

---

## 5. Structure du projet

```
Atihmam-ATS-Application/
│
├── backend/
│   ├── app/
│   │   ├── main.py                  # Point d'entrée FastAPI
│   │   ├── config/
│   │   │   ├── settings.py          # Configuration (pydantic-settings)
│   │   │   └── classification_rules.py  # Règles de classification des domaines
│   │   ├── api/v1/
│   │   │   ├── auth.py              # Routes authentification
│   │   │   ├── candidates.py        # CRUD candidats + transitions
│   │   │   ├── jobs.py              # CRUD postes
│   │   │   ├── ingestion.py         # Upload CV + webhooks Drive
│   │   │   ├── feedback.py          # Feedback recruteur (like/dislike)
│   │   │   └── analytics.py         # Statistiques et recommandations
│   │   ├── core/
│   │   │   ├── security.py          # JWT, get_current_user
│   │   │   └── state_machine.py     # Validation des transitions de statut
│   │   ├── db/
│   │   │   ├── supabase_client.py   # Clients Supabase (anon + admin)
│   │   │   └── drive_channels.py    # Canaux webhooks Drive
│   │   ├── models/                  # Modèles Pydantic (candidat, poste, user)
│   │   ├── services/
│   │   │   ├── ai_service.py        # Extraction CV + scoring final
│   │   │   ├── scoring_service.py   # Moteur de scoring principal
│   │   │   ├── intelligent_scoring_service.py  # Scoring avancé v2
│   │   │   ├── cv_parser.py         # Extraction texte PDF
│   │   │   ├── cv_classifier.py     # Classificateur de domaine
│   │   │   ├── drive_service.py     # Intégration Google Drive
│   │   │   └── webhook_manager.py   # Gestion des webhooks Drive
│   │   └── tasks/
│   │       ├── cv_processing.py     # Tâche Celery : traitement CV
│   │       └── drive_sync.py        # Tâche Celery : synchronisation Drive
│   ├── scripts/
│   │   └── backfill_now.py          # Re-scoring manuel en base
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── pyproject.toml
│   └── requirements.txt
│
└── frontend/
    ├── src/
    │   ├── api/
    │   │   ├── axiosClient.js       # Client Axios + intercepteurs auth
    │   │   ├── authApi.js           # Appels auth
    │   │   ├── candidatesApi.js     # Appels candidats
    │   │   └── jobsApi.js           # Appels postes
    │   ├── components/
    │   │   ├── Layout.jsx           # Sidebar + navigation
    │   │   ├── KanbanBoard.jsx      # Vue Kanban
    │   │   ├── Scorepanel.jsx       # Panneau de score détaillé
    │   │   ├── StatusBadge.jsx      # Badge de statut coloré
    │   │   ├── ScoreBadge.jsx       # Badge de score coloré
    │   │   ├── StatusTransitionModal.jsx  # Modal changement de statut
    │   │   └── UploadCVModal.jsx    # Modal upload de CV
    │   ├── hooks/                   # Hooks React Query (useCandidates, useJobs…)
    │   ├── pages/
    │   │   ├── Login.jsx            # Connexion + mot de passe oublié
    │   │   ├── ResetPassword.jsx    # Réinitialisation mot de passe
    │   │   ├── Dashboard.jsx        # Tableau de bord principal
    │   │   ├── CandidateList.jsx    # Liste des candidats
    │   │   ├── CandidateDetail.jsx  # Fiche candidat
    │   │   ├── JobList.jsx          # Liste des postes
    │   │   └── Analytics.jsx        # Page analytics
    │   ├── store/
    │   │   └── authStore.js         # État auth (Zustand + persistance)
    │   └── utils/
    │       └── domainClassifier.jsx # Classification côté frontend
    └── vite.config.js
```
<img width="426" height="676" alt="Screenshot 2026-06-02 114315" src="https://github.com/user-attachments/assets/14f04546-fa68-4c55-a51b-f47501b5f1b6" />

---

## 6. Installation et démarrage local

### Prérequis

- Python 3.11+
- Node.js 20+
- Un compte Supabase (gratuit)
- Une clé API Gemini (Google AI Studio)
- Valkey ou Redis en local (pour Celery)
- Un compte Google Cloud avec l'API Drive activée (optionnel)

### Backend

```bash
# Cloner le dépôt
git clone https://github.com/votre-repo/Atihmam-ATS-Application.git
cd Atihmam-ATS-Application/backend

# Copier le fichier de configuration
cp .env.example .env
# Remplir les valeurs dans .env (voir section Variables d'environnement)

# Installer les dépendances (avec uv, recommandé)
pip install uv
uv sync

# Ou avec pip classique
pip install -r requirements.txt

# Démarrer l'API
uvicorn app.main:app --reload --port 8000
```

L'API est accessible sur `http://localhost:8000`
La documentation Swagger est disponible sur `http://localhost:8000/docs`

### Worker Celery (optionnel, pour le traitement asynchrone des CVs)

```bash
# Dans un second terminal, depuis backend/
celery -A app.config.celery_config.celery_app worker --loglevel=info -P solo
```

### Frontend

```bash
cd frontend

# Installer les dépendances
npm install

# Copier et configurer l'environnement
cp .env.example .env
# Renseigner VITE_API_BASE_URL, VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY

# Démarrer le serveur de développement
npm run dev
```

L'application est accessible sur `http://localhost:5173`

### Avec Docker

```bash
# Depuis le dossier backend/
docker-compose up -d
```

Cela lance l'API, le worker Celery, Celery Beat et Valkey.

---

## 7. Variables d'environnement

### Backend (`.env`)

```env
# ── Supabase ──────────────────────────────────────────────
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...   # Clé admin, ne jamais exposer côté client

# ── JWT ───────────────────────────────────────────────────
SECRET_KEY=une-chaine-aleatoire-d-au-moins-64-caracteres
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# ── IA ────────────────────────────────────────────────────
GEMINI_API_KEY=AIza...             # Clé principale
DEEPSEEK_API_KEY=sk-...            # Fallback optionnel
MISTRAL_API_KEY=...                # Fallback optionnel

# ── Google Drive (optionnel) ──────────────────────────────
GOOGLE_DRIVE_CREDENTIALS_JSON=credentials.json
DRIVE_FOLDER_ID=1AbCdEfGhIjKlMnOpQ
WEBHOOK_BASE_URL=https://votre-domaine.com  # URL publique HTTPS

# ── Celery / Valkey ───────────────────────────────────────
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

# ── Application ───────────────────────────────────────────
APP_ENV=development
ALLOWED_ORIGINS=["http://localhost:5173"]
FRONTEND_URL=http://localhost:5173
```

### Frontend (`.env`)

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_SUPABASE_URL=https://xxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
```

---

## 8. API — Endpoints principaux

### Authentification (`/api/v1/auth`)

| Méthode | Route | Description |
|---------|-------|-------------|
| `POST` | `/auth/register` | Créer un compte |
| `POST` | `/auth/login` | Connexion, retourne un JWT |
| `POST` | `/auth/forgot-password` | Envoyer un email de réinitialisation |
| `POST` | `/auth/reset-password` | Changer le mot de passe |

### Candidats (`/api/v1/candidates`)

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/candidates` | Lister tous les candidats (filtrable par statut, poste) |
| `GET` | `/candidates/{id}` | Détail d'un candidat |
| `POST` | `/candidates` | Créer un candidat manuellement |
| `PATCH` | `/candidates/{id}` | Mettre à jour un candidat |
| `POST` | `/candidates/{id}/transition` | Changer le statut (avec validation) |
| `DELETE` | `/candidates/{id}` | Supprimer un candidat |
| `DELETE` | `/candidates` | Supprimer tous les candidats |
| `GET` | `/candidates/{id}/depth` | Analyse de profondeur du CV par IA |

### Postes (`/api/v1/jobs`)

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/jobs` | Lister les postes actifs |
| `GET` | `/jobs/{id}` | Détail d'un poste |
| `POST` | `/jobs` | Créer un poste |
| `PATCH` | `/jobs/{id}` | Modifier un poste |
| `DELETE` | `/jobs/{id}` | Désactiver un poste (soft delete) |

### Ingestion (`/api/v1/ingestion`)

| Méthode | Route | Description |
|---------|-------|-------------|
| `POST` | `/ingestion/upload` | Uploader un CV PDF (multipart/form-data) |
| `POST` | `/ingestion/drive/sync` | Déclencher une synchronisation Drive manuelle |
| `POST` | `/ingestion/drive/webhook` | Réception des notifications Drive (Google) |
| `POST` | `/ingestion/drive/register-webhook` | Enregistrer le webhook Drive (admin) |

### Analytics (`/api/v1/analytics`)

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/analytics/pipeline-stats` | Statistiques globales du pipeline |
| `GET` | `/analytics/recruiter-profile` | Profil IA du recruteur (basé sur les embauches) |
| `GET` | `/analytics/smart-recommendations` | Recommandations de candidats |
| `GET` | `/analytics/score-breakdown/{id}` | Analyse détaillée du score d'un candidat |
| `POST` | `/analytics/rescore-candidate/{id}` | Re-scorer un candidat |
| `POST` | `/analytics/rescore-all` | Re-scorer tous les candidats (tâche de fond) |

### Feedback (`/api/v1/feedback`)

| Méthode | Route | Description |
|---------|-------|-------------|
| `POST` | `/feedback/{id}/like` | Marquer un candidat comme bon profil |
| `POST` | `/feedback/{id}/dislike` | Marquer un candidat comme non adapté |
| `GET` | `/feedback/weights` | Consulter les poids adaptatifs actuels |
| `DELETE` | `/feedback/weights/reset` | Réinitialiser les poids aux valeurs par défaut |

---

## 9. Système de scoring IA

### Vue d'ensemble

Le scoring combine deux moteurs complémentaires.

**Moteur principal** (`scoring_service.py`) : scoring basé sur la sémantique et les mots-clés, avec détection automatique du domaine métier (30 secteurs) et pondérations adaptées à chaque secteur.

**Moteur intelligent** (`intelligent_scoring_service.py`) : scoring avancé avec déduplication de projets, calcul d'expérience réelle (sans double comptage), bonus d'écosystème technologique et apprentissage des préférences du recruteur.

### Les 7 dimensions du score

| Dimension | Description | Poids par défaut |
|-----------|-------------|------------------|
| Correspondance mots-clés | Mots-clés du CV présents dans l'offre d'emploi | 10% |
| Similarité sémantique | Comparaison de sens via SentenceTransformers | 20% |
| Expérience | Années d'expérience vs. exigences du poste | 15% |
| Certifications | AWS, Scrum, Oracle, etc. (domaines tech) | 10% |
| Complexité projets | Microservices, Kubernetes, production, etc. | 30% |
| Niveau d'études | Détection bac+2 / licence / master / doctorat | 10% |
| Leadership | Termes d'encadrement, management, etc. | 5% |

### Ajustements additifs

- **Depth bonus** (+20 pts max) : compétence utilisée en contexte réel dans le CV
- **Ecosystem bonus** (+10 pts max) : plusieurs technologies d'une même famille maîtrisées
- **Certification bonus** (+30 pts max) : certifications professionnelles reconnues
- **Recruiter fit bonus** (+20 pts max) : correspondance avec le profil des candidats embauchés par le recruteur
- **Diversity penalty** : pénalité si compétences trop concentrées dans un seul domaine
- **Repetition penalty** : pénalité si plusieurs projets se chevauchent dans le temps

### Apprentissage adaptatif

Lorsque le recruteur clique 👍 ou 👎 sur un candidat, les poids des dimensions qui ont le plus contribué au score sont ajustés en conséquence. Ces poids sont sauvegardés en base dans la table `app_config`. Un endpoint permet de les réinitialiser.

---

## 10. Pipeline de traitement des CVs

Voici les étapes exécutées par la tâche Celery `process_cv` après l'upload d'un CV :

```
Upload PDF
   │
   ▼
Vérification idempotence (déjà traité ?)
   │
   ▼
Téléchargement depuis Supabase Storage
   │
   ▼
Extraction texte brut (pdfplumber)
   │
   ▼
Extraction structurée par IA (Gemini → DeepSeek → Mistral → fallback)
   Résultat : nom, email, téléphone, compétences, historique de postes,
              projets, formations, langues, expérience totale
   │
   ▼
Scoring (comparaison avec le poste associé ou best-match parmi tous les postes actifs)
   │
   ▼
Sauvegarde en base (profil complet + score + dimensions)
   │
   ▼
Statut : "completed"
```

En cas d'erreur transitoire, la tâche est automatiquement relancée jusqu'à 3 fois avec un délai exponentiel (30s, 60s, 120s). Les erreurs permanentes (fichier illisible, candidat introuvable) marquent directement le statut `failed`.

### Fournisseurs IA et ordre de fallback

1. **NVIDIA** (modèle GLM)
2. **DeepSeek** (deepseek-chat)
3. **Mistral** (mistral-small-latest)
4. **Google Gemini** (gemini-3-flash)
5. **GitHub Models** (deepseek via Azure)

Le premier fournisseur disponible est utilisé. Si tous échouent, un profil vide est retourné.

---

## 11. Intégration Google Drive

### Principe

L'application peut surveiller un dossier Google Drive et importer automatiquement tout nouveau PDF déposé. Cela évite d'uploader les CVs un par un.

### Configuration initiale

1. Créer un projet sur Google Cloud Console
2. Activer l'API Google Drive
3. Créer des identifiants OAuth 2.0 (application bureau)
4. Télécharger le fichier `credentials.json` et le placer à la racine de `backend/`
5. Lancer une première fois pour générer `token.json` :

```bash
python -c "from app.services.drive_service import _get_drive_service; _get_drive_service()"
```

6. Renseigner `DRIVE_FOLDER_ID` dans `.env` avec l'identifiant du dossier Drive cible
7. Renseigner `WEBHOOK_BASE_URL` avec une URL HTTPS publique (utiliser ngrok en développement)

### Fonctionnement

- Un webhook Google est enregistré sur le dossier surveillé (canal de 7 jours, renouvelé automatiquement)
- À chaque nouveau fichier détecté, la tâche `process_drive_file` est mise en file d'attente
- La synchronisation complète (`sync_drive_folder`) peut être déclenchée manuellement depuis l'interface ou via l'API

---

## 12. Déploiement

### Backend sur Render

Le backend est configuré pour Render via le `Dockerfile` :

```dockerfile
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Variables d'environnement à configurer dans le dashboard Render : toutes les variables listées dans la section [Variables d'environnement](#7-variables-denvironnement).

### Frontend sur Vercel

Le frontend se déploie automatiquement depuis GitHub. Le fichier `vercel.json` gère la redirection pour React Router :

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

Variables d'environnement à configurer dans le dashboard Vercel :
- `VITE_API_BASE_URL` → URL du backend Render
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

### Configuration Supabase

Les tables suivantes doivent être créées dans votre projet Supabase :

| Table | Description |
|-------|-------------|
| `profiles` | Profils utilisateurs (id, full_name, role) |
| `candidates` | Données candidats complètes |
| `jobs` | Offres d'emploi |
| `candidate_status_history` | Historique des transitions de statut |
| `candidate_feedback` | Feedbacks recruteur |
| `drive_webhook_channels` | Canaux webhook Google Drive |
| `app_config` | Configuration dynamique (poids du scoring) |

Un bucket Supabase Storage nommé `cvs` est également nécessaire pour stocker les fichiers PDF.

---

## 13. Sécurité

- **JWT** : tous les endpoints (sauf `/auth/login` et `/auth/register`) nécessitent un token Bearer valide
- **Rôles** : certains endpoints (`/jobs` en écriture, `/ingestion/drive/register-webhook`) sont restreints aux rôles `admin` ou `recruiter`
- **Clé service Supabase** : utilisée uniquement côté serveur (tâches Celery, routes admin), jamais exposée au frontend
- **Fichiers sensibles** : `.env`, `credentials.json`, `token.json` sont dans `.gitignore`
- **CORS** : origines autorisées configurables via `ALLOWED_ORIGINS`
- **Webhooks Drive** : validés par l'état de la ressource (`x-goog-resource-state`)
- **Hash de fichier** : chaque CV est hashé (SHA-256) à l'upload pour éviter les doublons

> ⚠️ Ne jamais committer de fichiers `.env` ou de clés API dans le dépôt Git.

---

## Informations de déploiement

| Environnement | URL |
|---------------|-----|
| Frontend (Production) | https://atihmam-ats-application.vercel.app |
| Backend (Production) | https://atihmam-ats-application.onrender.com |
| Documentation API | https://atihmam-ats-application.onrender.com/docs |

---

*By Issika Kouamé — 2 juin 2026 *
