"""Les 6 scénarios du Tableau 1, avec leurs vérifications d'outil et de réponse.

Valeurs attendues calculées à la main sur le jeu de données de tests/fakes.py.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from boulangerie.tools import normaliser

Appel = dict  # {"name": str, "args": dict, "id": str}


@dataclass(frozen=True)
class Scenario:
    id: str
    titre: str
    question: str
    verifier_outils: Callable[[list[Appel]], str | None]
    verifier_reponse: Callable[[str], str | None]
    commande: bool = False
    relance: str | None = None


def _appels(appels: list[Appel], nom: str) -> list[dict]:
    return [a["args"] for a in appels if a["name"] == nom]


def _contient(texte: str, *options: str) -> bool:
    t = normaliser(texte).replace(" ", " ")
    return any(normaliser(o) in t for o in options)


def _outils_s1(appels):
    ok = any(a.get("table") == "stock" and _contient(a.get("recherche") or "beurre", "beurre")
             for a in _appels(appels, "consulter_boulangerie"))
    return None if ok else "consulter_boulangerie(table=stock, recherche=beurre) non appelé"


def _reponse_s1(texte):
    if not _contient(texte, "8 kg", "8kg", "8 kilos"):
        return "la quantité de beurre (8 kg) n'apparaît pas"
    return None if _contient(texte, "command") else "ne propose pas de commander alors que le beurre est sous le seuil"


def _outils_s2(appels):
    ok = any(a.get("table") == "ventes" and str(a.get("date_debut")) == "2026-02-09"
             and str(a.get("date_fin")) == "2026-02-15" for a in _appels(appels, "consulter_boulangerie"))
    return None if ok else "ventes du 2026-02-09 au 2026-02-15 non demandées"


def _reponse_s2(texte):
    return None if _contient(texte, "430") else "le total de 430 croissants n'apparaît pas"


def _outils_s3(appels):
    ok = any(a.get("table") == "catalogue" for a in _appels(appels, "consulter_boulangerie"))
    return None if ok else "catalogue non consulté"


def _reponse_s3(texte):
    return None if _contient(texte, "2,10", "2,1 ", "2.10", "2.1 ", "65,6", "65.6", "66 %", "66%") else (
        "ni la marge unitaire (2,10 €) ni le pourcentage (65,6 %) n'apparaissent"
    )


def _outils_s4(appels):
    commandes = _appels(appels, "passer_commande")
    if not commandes:
        return "passer_commande jamais appelé"
    args = commandes[-1]
    if normaliser(args.get("fournisseur", "")) != "minoterie dupont":
        return f"mauvais fournisseur : {args.get('fournisseur')!r}"
    if "50" not in args.get("produits", "") + args.get("corps", ""):
        return "la quantité de 50 kg n'est pas dans la commande"
    return None


def _reponse_s4(texte):
    return None if _contient(texte, "envoy", "parti", "est notee", "enregistr") else "ne confirme pas l'envoi"


def _outils_s5(appels):
    ok = any(str(a.get("date_cible")) == "2026-02-17" for a in _appels(appels, "prevoir_production"))
    return None if ok else "prevoir_production(date_cible=2026-02-17) non appelé"


def _reponse_s5(texte):
    return None if _contient(texte, "209") else "la recommandation de 209 baguettes n'apparaît pas"


def _outils_s6(appels):
    ok = any(a.get("table") == "stock" and (a.get("sous_seuil_uniquement") or not a.get("recherche"))
             for a in _appels(appels, "consulter_boulangerie"))
    return None if ok else "stock sous seuil non consulté"


def _reponse_s6(texte):
    manquants = [nom for nom in ("amande", "beurre", "levure") if not _contient(texte, nom)]
    return f"ingrédients urgents absents : {', '.join(manquants)}" if manquants else None


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("S1", "Stock bas", "Il me reste combien de beurre ? Faut que je commande ?", _outils_s1, _reponse_s1),
    Scenario("S2", "Ventes", "Combien de croissants j'ai vendu la semaine dernière ?", _outils_s2, _reponse_s2),
    Scenario("S3", "Marge", "C'est quoi ma marge sur les éclairs au chocolat ?", _outils_s3, _reponse_s3),
    Scenario(
        "S4",
        "Commande",
        "Prépare-moi un mail pour commander 50 kg de farine T65 chez Minoterie Dupont",
        _outils_s4,
        _reponse_s4,
        commande=True,
        relance="Oui, c'est parfait, envoie-le.",
    ),
    Scenario("S5", "Production", "Combien de baguettes je dois pétrir demain matin ?", _outils_s5, _reponse_s5),
    Scenario("S6", "Alerte pro-active", "Y a-t-il des trucs à commander en urgence ?", _outils_s6, _reponse_s6),
)
