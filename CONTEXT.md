# CONTEXT.md — La Boulangère Augmentée

## Objectif
Agent IA conversationnel qui aide Madeleine Croûton, boulangère, à gérer sa boulangerie.
Elle pose des questions en langage naturel, l'agent répond et agit.

## Stack
- **Framework agent** : LangChain (`create_react_agent`)
- **LLM** : Mistral Small (`mistral-small-latest`) via API Mistral
- **Interface** : Chainlit
- **BDD** : Notion API (librairie `notion-client`)
- **Email** : SMTP (`smtplib`)
- **Config** : `python-dotenv`

## Architecture

```
boulangerie-agent/
├── main.py              # Chainlit — interface utilisateur
├── agent.py             # Création agent LangChain
├── tools/
│   ├── __init__.py
│   ├── notion.py        # Tool lecture Notion
│   ├── email.py         # Tool envoi email + écriture Notion
│   └── prevision.py     # Tool prévision production
├── prompts/
│   └── system_prompt.txt
├── .env
├── .gitignore
├── requirements.txt
└── CONTEXT.md
```

## Variables d'environnement (.env)

```env
NOTION_TOKEN=<NOTION_TOKEN_REDACTED>


# IDs des data sources Notion (collection://...)
STOCK_DB_ID=<STOCK_DB_ID_REDACTED>
CATALOGUE_DB_ID=<CATALOGUE_DB_ID_REDACTED>
VENTES_DB_ID=<VENTES_DB_ID_REDACTED>
COMMANDES_DB_ID=<COMMANDES_DB_ID_REDACTED>

MISTRAL_API_KEY=# à remplir

SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=587
SMTP_USER=# à remplir
SMTP_PASS=# à remplir
SMTP_FROM=madeleine@chezMadeleine.fr
```

## Schémas des bases Notion

### 📦 Stock Ingrédients
| Colonne | Type |
|---------|------|
| `Ingrédient` | title |
| `Quantité en stock` | number |
| `Unité` | select (kg, L, unités, g) |
| `Seuil alerte` | number |
| `Fournisseur` | select |
| `Email fournisseur` | email |
| `Prix unitaire (€)` | number |
| `Dernière livraison` | date |

### 📊 Historique Ventes
| Colonne | Type |
|---------|------|
| `Vente` | title |
| `Produit` | select (12 produits) |
| `Quantité vendue` | number |
| `CA (€)` | number |
| `Date` | date |
| `Jour` | select (Lundi → Dimanche) |

### 🥖 Catalogue Produits
| Colonne | Type |
|---------|------|
| `Produit` | title |
| `Catégorie` | select (Pain, Viennoiserie, Pâtisserie, Snacking) |
| `Prix de vente TTC (€)` | number |
| `Coût de revient (€)` | number |
| `Marge (%)` | formula (calculée par Notion) |
| `Ingrédients principaux` | text |
| `Temps de préparation (min)` | number |
| `Disponible` | checkbox |

### 📋 Commandes Fournisseurs
Table vide — l'agent y écrit quand il passe une commande.
