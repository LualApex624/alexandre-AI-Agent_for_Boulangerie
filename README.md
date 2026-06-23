# 🥖 Gustave — Assistant IA de la Boulangerie Chez Madeleine

Gustave est un assistant IA conversationnel conçu pour aider **Madeleine Croûton**, boulangère artisanale, à gérer son quotidien : stocks d'ingrédients, ventes, commandes fournisseurs et prévisions de production.

Construit avec **Chainlit** (interface conversationnelle), **LangChain** (orchestration des outils) et **Mistral AI** (LLM), connecté à des bases **Notion** pour les données métier.

---

## ✨ Fonctionnalités

| Outil | Ce que Gustave peut faire |
|-------|--------------------------|
| 📦 **Stock** | Consulter les quantités disponibles, les seuils d'alerte, les fournisseurs et les emails |
| 📈 **Ventes** | Analyser les ventes par produit et par période, calculer le chiffre d'affaires |
| 🛒 **Catalogue** | Consulter les prix, les coûts de revient, les marges, les ingrédients et les temps de préparation |
| 📅 **Prévisions** | Calculer les quantités à produire par jour de la semaine |
| 📧 **Email** | Rédiger et envoyer des commandes fournisseurs par email |
| 🗂️ **Notion** | Enregistrer les commandes fournisseurs dans la base de données Notion |

---

## 🏗️ Architecture

```
AI_assistant_boulanger/
├── main.py                  # Interface Chainlit (gestion des sessions, starters)
├── agent.py                 # Configuration de l'agent LangChain + Mistral
├── prompts/
│   └── system_prompt.txt    # Prompt système de Gustave
├── tools/
│   ├── notion.py            # Outils : lire_stock, lire_ventes, lire_catalogue, enregistrer_commande
│   ├── email.py             # Outil : envoyer_email (SMTP)
│   └── prevision.py         # Outil : prevision_production
├── public/
│   ├── gustave.png          # Logo de l'assistant
│   └── style.css            # Thème CSS personnalisé (palette boulangerie)
├── .chainlit/
│   └── config.toml          # Configuration Chainlit (langue, logo, starters)
├── chainlit.md              # Page d'accueil de l'interface
├── requirements.txt         # Dépendances Python
└── .env.example             # Variables d'environnement à renseigner
```

---

## ⚙️ Installation

### 1. Cloner le projet

```bash
git clone https://github.com/arielYAPO/AI_assistant_boulanger.git
cd AI_assistant_boulanger
```

### 2. Créer et activer l'environnement virtuel

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer les variables d'environnement

Copie le fichier exemple et remplis tes clés :

```bash
cp .env.example .env
```

Ouvre `.env` et renseigne :

```env
# Mistral AI
MISTRAL_API_KEY=ta_cle_mistral

# Notion
NOTION_TOKEN=ton_token_notion
STOCK_DB_ID=id_de_ta_base_stock
VENTES_DB_ID=id_de_ta_base_ventes
CATALOGUE_DB_ID=id_de_ta_base_catalogue
COMMANDES_DB_ID=id_de_ta_base_commandes

# Email (SMTP)
SMTP_HOST=smtp.tonserveur.com
SMTP_PORT=587
SMTP_USER=ton_email@exemple.com
SMTP_PASS=ton_mot_de_passe
SMTP_FROM=ton_email@exemple.com
```

### 5. Lancer l'application

```bash
chainlit run main.py -w
```

L'interface s'ouvre sur [http://localhost:8000](http://localhost:8000).

---

## 🔧 Stack technique

| Composant | Technologie |
|-----------|-------------|
| Interface | [Chainlit](https://chainlit.io) |
| LLM | [Mistral AI](https://mistral.ai) — `mistral-small-latest` |
| Orchestration | [LangChain](https://www.langchain.com/) |
| Base de données | [Notion](https://notion.so) via API officielle |
| Email | SMTP Python (`smtplib`) |
| Langage | Python 3.12 |

---

## 📊 Données de démonstration

Le prototype utilise des données fictives couvrant la période du **2 au 15 février 2026** :
- 14 ingrédients en stock
- 12 produits au catalogue
- Historique de ventes sur 2 semaines
- Plusieurs fournisseurs locaux avec emails

---

## 📝 Variables d'environnement

| Variable | Description |
|----------|-------------|
| `MISTRAL_API_KEY` | Clé API Mistral AI |
| `NOTION_TOKEN` | Token d'intégration Notion |
| `STOCK_DB_ID` | ID de la base Notion des stocks |
| `VENTES_DB_ID` | ID de la base Notion des ventes |
| `CATALOGUE_DB_ID` | ID de la base Notion du catalogue |
| `COMMANDES_DB_ID` | ID de la base Notion des commandes |
| `SMTP_HOST` | Serveur SMTP pour l'envoi d'emails |
| `SMTP_PORT` | Port SMTP (généralement 587) |
| `SMTP_USER` | Identifiant de connexion SMTP |
| `SMTP_PASS` | Mot de passe SMTP |
| `SMTP_FROM` | Adresse email d'expédition |

---

*Boulangerie Chez Madeleine — Saint-Germain-des-Croissants* 🥐
