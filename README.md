# La Boulangère Augmentée Alexandre 🥐

Assistant IA conversationnel pour **Madeleine Croûton**, boulangère à Saint-Germain-des-Croissants. Alexandre lit ses stocks, ses ventes et son catalogue dans Notion, lui dit combien préparer pour le lendemain et prépare ses commandes fournisseurs : l'email ne part et la commande n'est enregistrée **qu'après son clic sur « Envoyer »**.

| Dossier | Contenu |
|---|---|
| [`alexandre/`](alexandre/) | **Alexandre**, la v2, réécrite selon le cahier des charges du test technique AI Sisters Lab |
| [`gustave/`](gustave/) | **Gustave**, le prototype v1, conservé tel quel à titre d'archive |

## Démarrage rapide (moins de 15 minutes)

Prérequis : Python 3.12 ou plus récent, une clé Gemini, un token d'intégration Notion avec accès aux 4 bases.

```bash
cd alexandre
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt    # versions figées (lockfile)
cp .env.example .env               # puis remplir .env (voir ci-dessous)
python -m boulangerie.serveur      # http://localhost:8000
```

Lancer depuis `alexandre/`. Le serveur n'écoute que sur `127.0.0.1` ; le port se change avec `PORT`.

Pour revoir l'interface **sans clé ni réseau** (données de test, modèle par mots-clés, aucun mail réel) : `python -m scripts.demo_hors_ligne` puis http://localhost:8001. Réservé au développement : ce n'est pas l'agent réel.

### Variables d'environnement (`alexandre/.env`)

| Variable | Obligatoire | Où la trouver |
|---|---|---|
| `GOOGLE_API_KEY` | oui | [Google AI Studio](https://aistudio.google.com/apikey) (niveau gratuit utilisable) |
| `LLM_MODEL` | non | défaut `gemini-3.5-flash` |
| `NOTION_TOKEN` | oui | Notion → Paramètres → Intégrations ; **partager les 4 bases avec l'intégration** |
| `STOCK_DB_ID`, `VENTES_DB_ID`, `CATALOGUE_DB_ID`, `COMMANDES_DB_ID` | oui | les 32 caractères hexadécimaux de l'URL de chaque base |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | non (tout ou rien) | [Mailtrap](https://mailtrap.io) → Sandboxes → SMTP. Sans ces variables, lecture et prévision fonctionnent ; l'envoi renvoie un message clair |
| `MISTRAL_API_KEY` | non | active Mistral comme modèle de secours |
| `DATE_REFERENCE` | non | « aujourd'hui » pour les données de démo, défaut `2026-02-16` |
| `PORT` | non | port du serveur web, défaut `8000` |

### Tests et évaluations

```bash
cd alexandre
.venv/bin/pytest                          # 108 tests et évals hors ligne, sans clé ni réseau
.venv/bin/python -m evals.run_evals --k 3 # évals live : vrai Gemini, 6 scénarios, pass@k
```

## Ce qu'Alexandre sait faire

Les 6 scénarios du cahier des charges (Tableau 1), vérifiés automatiquement par [`alexandre/evals/`](alexandre/evals/) :

| Madeleine demande… | Alexandre… |
|---|---|
| « Il me reste combien de beurre ? Faut que je commande ? » | lit le stock et le seuil, conseille, propose une commande |
| « Combien de croissants j'ai vendu la semaine dernière ? » | agrège les ventes du 09 au 15/02 |
| « C'est quoi ma marge sur les éclairs au chocolat ? » | lit le catalogue, donne la marge unitaire et le pourcentage |
| « Prépare-moi un mail pour commander 50 kg de farine T65 chez Minoterie Dupont » | rédige le mail, **attend la validation**, l'envoie puis enregistre la commande |
| « Combien de baguettes je dois pétrir demain matin ? » | estime la production à partir des mardis précédents |
| « Y a-t-il des trucs à commander en urgence ? » | liste les ingrédients sous leur seuil, du plus urgent au moins urgent |

## Interface

Une page sur mesure, fidèle à la maquette « Alexandre — assistant de boulangerie » (palette Farine, Dorure, Croûte, Four, Levain ; Fraunces pour les titres, DM Sans pour le texte ; mobile d'abord) :

- **Alexandre est un croissant animé** dont l'humeur suit l'état réel de l'agent : il respire au repos, se trémousse avec vapeur et anneau doré quand il pétrit sa réponse, rebondit avec une coche verte quand elle est prête. Le personnage tient dans un seul fichier, `web/avatar.svg`, à remplacer par le logo définitif.
- **Les appels d'outils restent visibles** (§9 du cahier) : étapes en direct pendant le travail, puis rappel au-dessus de la réponse.
- **Des cartes construites uniquement à partir des résultats d'outils** : Stock (jauge par rapport au seuil, bouton « Préparer la commande »), Ventes, Marge, Prévision (avec « estimation fragile » si peu d'historique), confirmation de commande.
- **Brouillon de commande** avec le vrai destinataire et les boutons « Envoyer » / « Ne pas envoyer », une décision par commande.
- **Alerte proactive** à l'ouverture : les ingrédients sous leur seuil, lus directement dans le stock, sans passer par le modèle.

## Architecture

```
Madeleine ─► page web (web/) ══WebSocket══► serveur FastAPI ─► Conversation ─► Agent LangGraph (create_agent)
                 ▲  boutons « Envoyer / Ne pas envoyer »                        │  ReAct : raisonne → appelle un outil → observe
                 └──────────────── interruption avant passer_commande ◄─────────┤
                                                                ├─► consulter_boulangerie ─► Notion (lecture paginée)
                                                                ├─► prevoir_production ────► Notion + Pandas
                                                                └─► passer_commande ───────► SMTP puis Notion (écriture)
```

| Module | Rôle |
|---|---|
| `web/` | Page, styles, logique (`app.js`, sans framework) et avatar (`avatar.svg`) |
| `boulangerie/serveur.py` | FastAPI : page statique, WebSocket, en-têtes de sécurité ; protocole documenté en tête du fichier |
| `boulangerie/cartes.py` | Cartes de l'interface, construites depuis les résultats d'outils du tour |
| `boulangerie/conversation.py` | Un fil de conversation : `envoyer`, `valider` (une décision par commande) ; messages clairs en cas de panne |
| `boulangerie/agent.py` | `create_agent` + middlewares : validation humaine, retry, secours Mistral, limite d'appels |
| `boulangerie/tools.py` | Les 3 outils et leur enveloppe de résultat commune ([contrat](alexandre/docs/tools.md)) |
| `boulangerie/notion_repo.py` | Accès Notion asynchrone : cache du `data_source_id`, pagination, parsing tolérant |
| `boulangerie/forecast.py` | Prévision : moyenne du même jour de la semaine × 1,1 |
| `boulangerie/prompts/system_prompt.md` | Prompt système (~100 lignes), calendrier injecté depuis `DATE_REFERENCE` |
| `boulangerie/config.py` | Configuration typée, lue une fois, secrets jamais affichés |

**Flux d'une question** : la page envoie le message par WebSocket → `agent.ainvoke` (non bloquant) → le modèle choisit un outil → l'outil renvoie une enveloppe JSON (`status`, `summary`, `data`, `next_actions`, `error`) → le modèle répond à partir de `data` uniquement → l'état complet, messages d'outils compris, est conservé pour le tour suivant.

**Flux d'une commande** : le modèle appelle `passer_commande` → le graphe **s'arrête avant l'exécution** → Madeleine voit le brouillon et le vrai destinataire → « Envoyer » reprend le graphe → email SMTP puis ligne dans Commandes Fournisseurs (référence `CMD-AAAAMMJJ-XXXX`, statut « Envoyée », corps du mail dans *Notes*). Une seule validation couvre les deux actions.

## Choix techniques

| Couche | Choix | Pourquoi |
|---|---|---|
| Orchestration | LangChain 1.x `create_agent` (graphe LangGraph) | un seul interlocuteur, interruption native avant une action irréversible, checkpointer pour l'historique ; voir l'[ADR 0001](alexandre/docs/adr/0001-langgraph-plutot-que-crewai.md) (LangGraph plutôt que CrewAI) |
| LLM | Gemini `gemini-3.5-flash`, Mistral en secours optionnel | niveau gratuit, tool calling fiable en français ; `gemini-2.5-flash` n'est plus ouvert aux nouvelles clés |
| Interface | Page sur mesure (HTML/CSS/JS natif) servie par FastAPI, WebSocket | fidèle à la maquette, personnage animé selon l'état de l'agent, aucune chaîne de build ; écart assumé au §9 (Chainlit), voir l'[ADR 0002](alexandre/docs/adr/0002-frontend-sur-mesure-plutot-que-chainlit.md) |
| Données | Notion (`notion-client` asynchrone) | imposé par le test ; 4 bases fournies |
| Email | SMTP STARTTLS (`smtplib` hors boucle d'événements) | envoi réel exigé ; Mailtrap évite tout spam |
| Prévision | Pandas | calcul simple, transparent, explicable à Madeleine |
| Config | python-dotenv + dataclass typée | secrets hors dépôt, chargement unique, erreur claire au démarrage |
| Qualité | pytest (TDD), évaluations déterministes | le critère « aucun chiffre inventé » ne se vérifie que par des tests |

### Décisions prises avant de coder

1. **Validation dans le code, pas seulement dans le prompt** : interruption du graphe avant `passer_commande`, plus un jeton de validation exigé par l'outil lui-même.
2. **Une seule validation pour l'email et l'écriture Notion**, regroupés dans un même outil.
3. **Échec partiel** : si l'email part mais que Notion échoue, Madeleine est prévenue, la commande est gardée dans `var/commandes_non_tracees.jsonl`, et l'agent a pour consigne de ne jamais relancer l'envoi.
4. **Date de référence en configuration** (`DATE_REFERENCE`), injectée dans le prompt.
5. **Le destinataire n'est jamais choisi par le modèle** : l'adresse est lue dans la base Stock.

## Gustave v1 → Alexandre v2

| Exigence | Gustave v1 | Alexandre v2 |
|---|---|---|
| A01 Secrets | token Notion commité dans `CONTEXT.md` | `.env` uniquement, test « aucun secret dans le dépôt » |
| A02 Asynchrone | `agent.invoke` bloquant dans un handler async | `ainvoke`, Notion asynchrone, SMTP dans un thread |
| A03 Pagination | 100 lignes maximum, troncature silencieuse | boucle `has_more` / `next_cursor` |
| A04 Historique | textes seuls, résultats d'outils perdus | checkpointer LangGraph, messages d'outils conservés |
| A05 Dépendances | aucune version figée | `requirements.txt` figé (lockfile) |
| A06 Confirmation | consigne dans le prompt | interruption du graphe + jeton exigé par l'outil |
| A07 Prévision | moyenne × 1,1 sans contexte | fenêtre glissante, nombre d'observations, avertissement si estimation fragile |
| A08 Erreurs | exceptions affichées telles quelles | enveloppe d'erreur pour le modèle, message simple pour Madeleine |

## Sécurité

Détails et preuves : [`alexandre/docs/securite.md`](alexandre/docs/securite.md). En résumé : contenu Notion traité comme donnée non fiable (nettoyé, borné), validations déterministes juste avant chaque effet de bord, images et liens markdown neutralisés dans l'interface, serveur local uniquement, secrets absents des logs et du dépôt.

> **Attention** : l'historique git contient encore le token Notion commité dans la v1 (commit `42dc923`). Il faut le considérer comme compromis et le régénérer.

## Limites assumées

- **Prévision fragile** : les données de démo couvrent environ deux semaines (02 au 15/02/2026), soit une ou deux observations par jour de la semaine. La moyenne × 1,1 est donc très approximative ; l'outil renvoie le nombre d'observations et Alexandre le signale.
- Historique perdu au redémarrage (checkpointer en mémoire), pas d'authentification ni de multi-utilisateur : prototype local pour une seule personne.
- Dépendance au niveau gratuit de Gemini : quota journalier et limites de débit possibles en démonstration intensive (erreur `429`). Renseigner `MISTRAL_API_KEY` active un modèle de secours.
- Calendrier figé par `DATE_REFERENCE` pour coller aux données de démo.
- Pas de streaming du texte : les appels d'outils s'affichent au fil de l'eau, la réponse s'affiche d'un bloc à la fin du tour (`ainvoke`, comme le flux du §5.3 du cahier).
- Une nouvelle conversation démarre à chaque connexion (rechargement de la page, bouton ↻) : l'historique est gardé tant que la page reste ouverte.
- Trois outils au lieu de « 4 à 6 fonctions » (§5.2) : la lecture Notion est un outil unique paramétré, ce que le §7.1 autorise, et l'envoi d'email et l'écriture Notion forment un seul outil pour qu'une seule validation couvre les deux (décision D2).

## État de validation

Commande réelle vérifiée de bout en bout le 09/11/2026 (email SMTP Mailtrap sandbox + ligne Notion). Les évaluations live avec k = 3 restent à rejouer quand le quota Gemini le permet (`python -m evals.run_evals --k 3`). Détail dans [`alexandre/docs/TICKETS.md`](alexandre/docs/TICKETS.md).

## Pistes d'amélioration

- Ajuster la prévision selon la météo ([Open-Meteo](https://open-meteo.com), gratuit, sans clé) : moins de passage les jours de pluie.
- Persister les conversations (checkpointer SQLite ou Postgres).
- Streamer la réponse finale token par token (`astream` + trames WebSocket).
- Dictée vocale (le micro de la maquette), avec un service de reconnaissance de la parole.
- Relance automatique des commandes gardées en trace locale.
- Authentification si l'interface doit être exposée au-delà du poste local.
- Évaluations live dans la CI avec une clé dédiée, et suivi du pass@k dans le temps.

## Documentation

- [Tickets et décisions](alexandre/docs/TICKETS.md) — découpage du cahier des charges
- [Contrat des outils](alexandre/docs/tools.md)
- [Évaluations](alexandre/evals/README.md)
- [Sécurité](alexandre/docs/securite.md)
- [ADR](alexandre/docs/adr/README.md) — LangGraph plutôt que CrewAI, interface sur mesure plutôt que Chainlit
