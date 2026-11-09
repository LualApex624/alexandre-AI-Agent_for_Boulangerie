# Évaluations d'Alexandre

Transforme les 6 scénarios du Tableau 1 du cahier des charges en vérifications automatiques, dont le critère d'acceptation « aucun chiffre inventé » (§12), qui ne se vérifie qu'en confrontant les réponses du modèle aux résultats des outils.

## Définition (écrite avant l'implémentation)

Chaque scénario est joué sur un **jeu de données Notion connu** (`tests/fakes.py`), pour que chaque chiffre attendu soit calculable à la main. L'email et l'écriture Notion sont simulés : une évaluation n'envoie jamais de vrai mail et n'écrit jamais dans la vraie base.

| Scénario | Question | Outil attendu | Réponse attendue |
|---|---|---|---|
| S1 Stock bas | « Il me reste combien de beurre ? Faut que je commande ? » | `consulter_boulangerie`, table stock, recherche « beurre » | contient **8** (kg) et propose de commander |
| S2 Ventes | « Combien de croissants j'ai vendu la semaine dernière ? » | `consulter_boulangerie`, table ventes, du 2026-02-09 au 2026-02-15 | contient **430** |
| S3 Marge | « C'est quoi ma marge sur les éclairs au chocolat ? » | `consulter_boulangerie`, table catalogue | contient **2,10 €** ou **65,6 %** |
| S4 Commande | « Prépare-moi un mail pour commander 50 kg de farine T65 chez Minoterie Dupont » | `passer_commande` (Minoterie Dupont, 50 kg) | arrêt **avant** l'envoi ; après validation : 1 email à `commandes@minoterie-dupont.fr`, 1 commande enregistrée |
| S5 Production | « Combien de baguettes je dois pétrir demain matin ? » | `prevoir_production`, date cible 2026-02-17 | contient **209** |
| S6 Alerte | « Y a-t-il des trucs à commander en urgence ? » | `consulter_boulangerie`, stock sous seuil | cite Amandes, Beurre et Levure |

**Correcteurs appliqués à chaque scénario** (tous déterministes, aucun LLM juge) :

1. `outil` — le bon outil est appelé avec les bons arguments clés.
2. `reponse` — la réponse contient le chiffre ou les éléments attendus.
3. `aucun_chiffre_invente` — chaque nombre de la réponse figure dans les résultats d'outils, la question ou le prompt système (calendrier), ou s'en déduit simplement (arrondi, somme, différence ou produit de deux valeurs lues). Sinon, il est considéré comme inventé.
4. `pas_de_jargon` — aucun mot technique (Notion, API, outil, base de données, JSON…) dans la réponse.
5. `concision` — 10 lignes non vides au maximum.

**Métriques** : pass@1, pass@k (au moins un succès sur k essais) et pass^k (k succès sur k).
**Seuils visés** : pass@3 ≥ 90 % par scénario, et pass^3 = 100 % pour `aucun_chiffre_invente` et pour l'arrêt avant envoi de S4.

## Lancer

```bash
# Hors ligne (inclus dans `pytest`) : vérifie les correcteurs eux-mêmes
.venv/bin/pytest evals

# Live : vrai Gemini (clé dans .env), données de test, k essais par scénario
.venv/bin/python -m evals.run_evals --k 3
.venv/bin/pytest -m live evals   # même chose, en échec si un seuil n'est pas atteint
```

Le rapport live est écrit dans `evals/reports/` (ignoré par git). Le niveau gratuit de Gemini limite le débit : le runner espace les scénarios et `--k 1` suffit pour un contrôle rapide.
