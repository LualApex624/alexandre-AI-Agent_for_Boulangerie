# Contrats des outils d'Alexandre

Trois outils, un par besoin du cahier des charges (§7). Ce document fixe leurs noms, leurs paramètres et la forme exacte de leurs résultats **avant** l'implémentation ; les tests vérifient ce contrat.

## Principes

1. **Noms stables et métier** : le modèle choisit l'outil d'après son nom et sa description, écrits en français comme les questions de Madeleine.
2. **Paramètres étroits et typés** (`Literal`, `date`, bornes) : une valeur invalide est rejetée avec une explication, pas devinée.
3. **Une seule forme de résultat** pour les trois outils (enveloppe JSON ci-dessous), quel que soit le cas : succès, avertissement ou erreur.
4. **Les chiffres viennent de `data`** et seulement de là. Le prompt interdit d'en donner un qui n'y figure pas ; les évaluations le vérifient.
5. **Le contenu lu dans Notion est une donnée non fiable** : il est rangé dans `data` et ne doit jamais être interprété comme une instruction.
6. **Jamais d'exception vers le modèle ou l'interface** : toute erreur devient une enveloppe `status: "error"` avec un code, une cause, une consigne de reprise et une condition d'arrêt.

## Enveloppe de résultat

```json
{
  "status": "success | warning | error",
  "summary": "Une phrase, fidèle aux données.",
  "data": { "...": "données structurées, seule source autorisée pour les chiffres" },
  "next_actions": ["Ce que l'agent peut faire ensuite."],
  "artifacts": { "reference": "CMD-20261109-7F3A" },
  "error": {
    "code": "PERIODE_MANQUANTE",
    "cause": "Pourquoi ça a échoué.",
    "retry": "Comment réessayer sans risque, ou « ne pas réessayer ».",
    "stop": "Quand abandonner et quoi dire à Madeleine."
  }
}
```

- `warning` = l'outil a répondu mais le résultat est vide, partiel ou fragile (aucune correspondance, période sans données, prévision sur peu d'observations, échec partiel d'une commande).
- `artifacts` et `error` ne sont présents que lorsqu'ils ont un contenu.
- Montants arrondis à 2 décimales, en euros ; dates au format ISO `AAAA-MM-JJ`.

## Outil 1 — `consulter_boulangerie` (lecture Notion, F03)

Un outil paramétré plutôt que trois : les trois lectures partagent la même mécanique (pagination, cache du `data_source_id`, recherche tolérante) et le paramètre `table` est un `Literal` sans ambiguïté.

| Paramètre | Type | Règle |
|---|---|---|
| `table` | `"stock" \| "ventes" \| "catalogue"` | obligatoire |
| `recherche` | `str \| None` | mot-clé sur le nom (ingrédient ou produit), insensible à la casse et aux accents ; absent = tout |
| `date_debut`, `date_fin` | `date \| None` | **obligatoires pour `ventes`**, ignorés ailleurs ; `date_debut ≤ date_fin` |
| `sous_seuil_uniquement` | `bool` | `stock` uniquement : ne garder que les ingrédients dont la quantité est ≤ au seuil d'alerte |

Toutes les lignes sont lues avec pagination (`has_more` / `next_cursor`) puis filtrées localement : cela permet une recherche tolérante (« amande » trouve « Amandes en poudre ») que le filtre `contains` de Notion ne donne pas.

**`data` selon la table**

- `stock` : `{"items": [{"ingredient", "quantite", "unite", "seuil_alerte", "sous_seuil", "fournisseur", "email_fournisseur", "prix_unitaire", "derniere_livraison"}], "nb_resultats"}`
- `ventes` : `{"periode": {"debut", "fin"}, "par_produit": [{"produit", "quantite", "ca"}], "total_quantite", "total_ca", "nb_lignes", "donnees_disponibles": {"debut", "fin"}}`
- `catalogue` : `{"items": [{"produit", "categorie", "prix_vente_ttc", "cout_revient", "marge_unitaire", "marge_pct", "ingredients", "temps_preparation_min", "disponible"}], "nb_resultats"}`

`marge_unitaire = prix_vente_ttc − cout_revient`, calculée par l'outil pour que le modèle n'ait pas à faire d'arithmétique.

**Erreurs et avertissements**

| Code / cas | Status | Consigne |
|---|---|---|
| `PERIODE_MANQUANTE` | error | Demander la période à Madeleine. Ne pas inventer de dates. |
| `PARAMETRE_INVALIDE` (`sous_seuil_uniquement` hors stock, `date_debut > date_fin`) | error | Corriger l'appel une fois. |
| Aucune correspondance | warning | Réessayer une fois avec un mot-clé plus court ; sinon dire qu'on ne trouve pas. |
| Période sans vente | warning | Dire que les données couvrent `donnees_disponibles`. |
| `NOTION_INDISPONIBLE` | error | Réessayer une fois ; sinon dire à Madeleine que ses données sont inaccessibles pour l'instant. |

## Outil 2 — `passer_commande` (email SMTP + écriture Notion, F04)

**Action irréversible.** Le graphe s'interrompt **avant** son exécution et attend la validation de Madeleine dans l'interface (D1). Une seule validation couvre l'envoi et l'écriture (D2).

| Paramètre | Type | Règle |
|---|---|---|
| `fournisseur` | `str` | doit correspondre à un fournisseur de la base Stock |
| `produits` | `str` | produits et quantités, ex. « 50 kg de Farine T65 » |
| `objet` | `str` | 1 à 150 caractères, sans retour à la ligne |
| `corps` | `str` | 1 à 3 000 caractères, texte brut |
| `montant_estime` | `float \| None` | ≥ 0, calculé à partir des prix unitaires lus dans le stock |

**Pas de paramètre d'adresse email** (D6) : l'outil lit l'adresse du fournisseur dans la base Stock.

Déroulé : résolution du fournisseur → envoi SMTP (STARTTLS) → `pages.create` dans Commandes Fournisseurs (référence `CMD-AAAAMMJJ-XXXX`, statut « Envoyée », corps de l'email dans *Notes*).

| Cas | Status | `artifacts` | Consigne |
|---|---|---|---|
| Succès | success | `reference`, `notion_page_id` | Dire que l'email est parti et que la commande est notée. |
| `FOURNISSEUR_INCONNU` | error | — | Rien n'a été envoyé. `data.fournisseurs_connus` liste les noms valides ; reproposer la commande. |
| `EMAIL_ECHEC` | error | — | Rien n'a été envoyé ni noté. Ne pas réessayer seul ; prévenir Madeleine. |
| `COMMANDE_NON_TRACEE` (email parti, Notion en échec) | warning | `reference`, `trace_locale` | **Ne jamais relancer** (l'email partirait deux fois). Dire que l'email est parti mais que la commande n'est pas notée ; elle est gardée en trace locale (D3). |
| Refus de Madeleine | — | — | L'outil ne s'exécute pas ; le graphe renvoie un message de refus. Ne rien envoyer. |

## Outil 3 — `prevoir_production` (prévision, F05 / A07)

| Paramètre | Type | Règle |
|---|---|---|
| `date_cible` | `date` | jour à préparer ; « demain » est résolu à partir de la date de référence du prompt |
| `produit` | `str \| None` | mot-clé ; absent = tous les produits |
| `fenetre_jours` | `int` | 7 à 90, défaut 28 : historique pris en compte avant la date cible |

Calcul : ventes de la fenêtre qui tombent le **même jour de la semaine** que la date cible → moyenne par produit → × 1,1 → arrondi à l'unité.

`data` : `{"date_cible", "jour", "fenetre": {"debut", "fin"}, "coefficient": 1.1, "produits": [{"produit", "observations", "moyenne", "recommandation"}]}`

| Cas | Status | Consigne |
|---|---|---|
| Estimation sur au moins 3 observations par produit | success | Donner les recommandations. |
| Au moins un produit avec moins de 3 observations | warning | Donner les chiffres en précisant que l'estimation est fragile (D4). |
| Aucun historique pour ce jour | warning | Le dire ; ne pas inventer de quantité. |
| `NOTION_INDISPONIBLE` | error | Comme pour l'outil 1. |
