# Tickets — Alexandre (v2)

Découpage du *Cahier des charges — Agent IA Boulangerie* (v1.0, 09/11/2026) en tickets livrables un par un, chacun clos par un commit.
Références : `Fxx` exigences obligatoires (§4.1), `Axx` améliorations par rapport à Gustave v1 (§4.2), `Sx` scénarios du Tableau 1 (§2.1), `Cx` critères d'acceptation (§12), `Dx` décisions prises avant de coder (ci-dessous).

## Décisions prises avant de coder

| ID | Sujet | Décision |
|---|---|---|
| D1 | Confirmation d'email (A06) | Verrou **dans le code** : le graphe LangGraph s'interrompt avant l'exécution de `passer_commande` (`HumanInTheLoopMiddleware`). Sans validation de Madeleine dans l'interface, l'outil ne s'exécute pas, quoi que dise le modèle. |
| D2 | Deux actions irréversibles (§7.2, §8) | Envoi de l'email et écriture Notion sont regroupés dans **un seul outil**, couvert par **une seule confirmation**. |
| D3 | Échec partiel | Si l'email part mais que l'écriture Notion échoue : message clair à Madeleine (« email parti, commande pas encore notée ») et trace locale de la commande (`var/commandes_non_tracees.jsonl`) pour ressaisie. |
| D4 | Prévision | Avec ~2 semaines de données, il n'y a que ~2 observations par jour de semaine. L'outil renvoie le nombre d'observations et signale une estimation fragile ; le README le dit. |
| D5 | Date de référence | « Aujourd'hui » (16/02/2026) passe en configuration (`DATE_REFERENCE`) et est injecté dans le prompt, au lieu d'être écrit en dur. |
| D6 | Destinataire de l'email (sécurité) | Le modèle ne fournit pas l'adresse : l'outil la lit dans la base Stock à partir du nom du fournisseur. Un contenu malveillant ne peut pas faire envoyer un email à une adresse arbitraire. |

## Tickets

| # | Ticket | Couvre | Critère de fin |
|---|---|---|---|
| T01 | Archiver Gustave v1 dans `gustave/`, retirer le token du dépôt | A01, C7 | Plus aucun secret dans l'arbre de travail ✅ |
| T02 | Découpage en tickets (ce document) | — | Document commité |
| T03 | Contrats des 3 outils (noms, paramètres, forme des résultats, erreurs) | F03–F05, A08 | `docs/tools.md` validé avant le code |
| T04 | Socle projet : `pyproject.toml`, dépendances figées (lockfile), `.env.example`, configuration typée chargée une fois | F07, A01, A05, D5 | `pip install -r requirements.txt` reproductible ; config invalide = erreur claire au démarrage |
| T05 | Accès Notion asynchrone : cache du `data_source_id`, pagination `has_more`/`next_cursor`, parsing typé | F03, A02, A03 | Tests : 3 pages agrégées, cache appelé une fois, ligne mal formée ignorée sans planter |
| T06 | Outil 1 `consulter_boulangerie` (stock, ventes, catalogue, alertes) | F03, S1, S2, S3, S6 | Tests : chaque table, filtre, période obligatoire pour les ventes, alertes sous seuil, erreurs lisibles |
| T07 | Outil 3 `prevoir_production` (fenêtre glissante, jour cible, ×1,1, nb d'observations) | F05, A07, S5, D4 | Tests : calcul exact sur jeu connu, jour sans historique, avertissement si < 3 observations |
| T08 | Outil 2 `passer_commande` (email SMTP + écriture Notion, référence unique, échec partiel) | F04, A06, S4, D2, D3, D6 | Tests : succès, échec SMTP, échec Notion après envoi, fournisseur inconnu, injection d'en-tête |
| T09 | Agent LangGraph : `create_agent`, interruption avant `passer_commande`, historique complet (checkpointer), retry/fallback LLM | F01, F02, A02, A04, A06, D1 | Tests : le graphe s'arrête avant l'outil ; refus = aucun envoi ; ToolMessages conservés entre tours |
| T10 | Prompt système (80–120 lignes) : persona, anti-hallucination, table question → outil, calendrier injecté, règles d'action, données non fiables | F06, §8 | Test : le prompt rendu contient la date de référence et les règles clés |
| T11 | Interface Chainlit : `ainvoke`/stream non bloquant, tool calls visibles, boutons de validation, messages d'erreur clairs, thème, 3–4 starters | F07, A02, A08, §9, C5 | Démo manuelle ; aucune stacktrace visible côté Madeleine |
| T12 | Évaluations : les 6 scénarios du Tableau 1 + vérification « aucun chiffre inventé » | C1, C2, C4 | `pytest evals` vert hors ligne ; runner live (vrai LLM) documenté |
| T13 | Durcissement sécurité : secrets, contenu Notion traité comme donnée non fiable, test « aucun secret dans le dépôt » | A01, C7, D6 | Revue sécurité sans constat bloquant |
| T14 | ADR 0001 LangGraph vs CrewAI | §5.1, §6.1, §10 | `docs/adr/0001-*.md` |
| T15 | README complet (installation < 15 min, architecture, choix, limites, pistes) | F08, C6 | Un tiers lance le projet en suivant le README |
| T16 | Revue de code avant livraison et corrections | — | Constats traités ou documentés |

## Scénarios du Tableau 1 → outils

| Scénario | Question de Madeleine | Outil(s) attendu(s) |
|---|---|---|
| S1 Stock bas | « Il me reste combien de beurre ? Faut que je commande ? » | `consulter_boulangerie(table="stock", recherche="beurre")` |
| S2 Ventes | « Combien de croissants j'ai vendu la semaine dernière ? » | `consulter_boulangerie(table="ventes", recherche="croissant", date_debut="2026-02-09", date_fin="2026-02-15")` |
| S3 Marge | « C'est quoi ma marge sur les éclairs au chocolat ? » | `consulter_boulangerie(table="catalogue", recherche="éclair")` |
| S4 Commande | « Prépare-moi un mail pour commander 50 kg de farine T65 chez Minoterie Dupont » | `consulter_boulangerie(stock)` puis `passer_commande` → **validation de Madeleine** → envoi + écriture Notion |
| S5 Production | « Combien de baguettes je dois pétrir demain matin ? » | `prevoir_production(date_cible="2026-02-17")` |
| S6 Alerte proactive | « Y a-t-il des trucs à commander en urgence ? » | `consulter_boulangerie(table="stock", sous_seuil_uniquement=True)` |

## Hors périmètre (assumé, §13)

Persistance longue des sessions, multi-utilisateur et authentification, ajustement météo de la prévision (Open-Meteo, documenté comme piste).
