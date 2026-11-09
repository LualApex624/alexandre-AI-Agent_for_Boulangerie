# ADR-0001 : Un agent unique LangGraph (`create_agent`) plutôt qu'un équipage CrewAI

**Date** : 2026-11-09
**Statut** : accepté
**Décideurs** : Paul-Alex Yao

## Contexte

Madeleine a besoin d'**un seul interlocuteur** patient qui lit ses données, calcule une prévision et passe des commandes (§2, §5.1 du cahier des charges). Le test impose un framework d'orchestration open-source et au moins 3 outils, dont une action **irréversible** (email + écriture Notion) qui doit attendre sa validation explicite (§2.2, A06). La conversation s'étend sur plusieurs tours et doit garder les résultats d'outils (A04). Le prototype doit rester simple à démontrer en 30 minutes et à faire tourner en local en moins de 15 minutes.

## Décision

Alexandre est **un agent tool-calling unique** construit avec `langchain.agents.create_agent` (LangChain 1.x), qui compile une boucle ReAct en **graphe LangGraph**. Les besoins transverses passent par des middlewares : `HumanInTheLoopMiddleware` (arrêt avant `passer_commande`), `ModelRetryMiddleware`, `ModelFallbackMiddleware` (Mistral en secours) et `ModelCallLimitMiddleware`. L'état de chaque conversation est conservé par un checkpointer LangGraph (`InMemorySaver`), un fil par session.

## Alternatives considérées

### CrewAI (équipage multi-agents)
- **Pour** : séparation nette des rôles (analyste stock → rédacteur → superviseur), bien adapté aux workflows multi-étapes.
- **Contre** : plusieurs appels au modèle par question (latence et coût en tokens, sensibles sur un niveau gratuit), orchestration à expliquer, et validation humaine moins naturelle au niveau d'un appel d'outil précis.
- **Pourquoi pas** : aucun gain métier perceptible pour une utilisatrice unique qui pose des questions courtes ; la complexité ajoutée ne sert aucun besoin du cahier des charges (§6.1, §10.2).

### `StateGraph` LangGraph écrit à la main
- **Pour** : contrôle total des nœuds et des transitions.
- **Contre** : réécrire la boucle ReAct, la gestion des appels d'outils et l'interruption, que `create_agent` et ses middlewares fournissent déjà et testent.
- **Pourquoi pas** : plus de code pour le même comportement. L'option reste ouverte : `create_agent` produit un `StateGraph` compilé, on peut en sortir sans changer de framework.

### Smolagents
- **Pour** : léger, agents qui écrivent du code pour enchaîner les actions.
- **Contre** : exécuter du code généré par le modèle élargit fortement la surface d'attaque, alors que le contenu Notion est une donnée non fiable.
- **Pourquoi pas** : incompatible avec l'exigence de validations déterministes avant chaque effet de bord.

### LangChain sans LangGraph (chaîne ou agent « classique »)
- **Pour** : encore plus simple.
- **Contre** : ni interruption native, ni checkpointer pour l'historique complet.
- **Pourquoi pas** : ne couvre ni A04 ni le verrou de validation D1.

## Conséquences

### Positives
- Le verrou de validation est dans le graphe, pas dans le prompt : `tests/test_conversation.py` prouve que rien ne part sans validation et qu'un refus est transmis au modèle.
- L'historique complet (messages d'outils compris) est conservé entre les tours sans code dédié.
- Une seule boucle, un seul modèle par appel : latence et coût minimaux, facile à expliquer en démonstration.
- Pattern aligné sur les exemples de référence « inventory & order » de l'écosystème LangGraph (§10.1).

### Négatives
- Dépendance à l'API de LangChain 1.x, qui évolue vite (middlewares récents).
- `InMemorySaver` : l'historique est perdu au redémarrage (limite assumée, §13).
- Les middlewares masquent une partie du graphe : il faut lire leur code pour comprendre l'ordre d'exécution.

### Risques
- **Changement d'API LangChain/LangGraph** : versions figées dans `requirements.txt` ; les tests du point d'entrée B échouent immédiatement si le comportement d'interruption change.
- **Besoin futur de vrais rôles séparés** (ex. un agent de planification hebdomadaire) : passer à un `StateGraph` explicite avec sous-graphes, sans changer de framework, et le consigner dans un nouvel ADR.
