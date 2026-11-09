"""Cartes de l'interface, construites uniquement à partir des résultats d'outils.

Règle « aucun chiffre inventé » : chaque nombre affiché vient du champ `data`
d'une enveloppe d'outil. Les seules valeurs calculées ici sont des proportions
de dessin (largeur d'une jauge ou d'une barre, entre 0 et 1), jamais affichées
comme des chiffres.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

MAX_LIGNES = 6


@dataclass(frozen=True)
class ResultatOutil:
    outil: str
    enveloppe: dict[str, Any]


def _jj_mm(iso: str) -> str:
    jour = date.fromisoformat(iso)
    return f"{jour:%d/%m}"


def _barres(lignes: list[tuple[str, float]]) -> list[dict]:
    maximum = max((valeur for _, valeur in lignes), default=0) or 1
    return [
        {"libelle": libelle, "valeur": valeur, "part": round(valeur / maximum, 2)}
        for libelle, valeur in lignes[:MAX_LIGNES]
    ]


def _stock(data: dict) -> dict | None:
    items = [
        {
            "ingredient": i["ingredient"],
            "quantite": i["quantite"],
            "unite": i["unite"],
            "seuil_alerte": i["seuil_alerte"],
            "sous_seuil": i["sous_seuil"],
            "fournisseur": i["fournisseur"],
            # Jauge : remplissage par rapport au seuil d'alerte (pleine au-delà).
            "niveau": round(min(i["quantite"] / i["seuil_alerte"], 1.0), 2)
            if i["quantite"] is not None and i["seuil_alerte"]
            else None,
        }
        for i in data.get("items", [])[:MAX_LIGNES]
    ]
    if not items:
        return None
    if len(items) == 1:
        titre = f"Stock · {items[0]['ingredient']}"
    elif all(i["sous_seuil"] for i in items):
        titre = "À commander en priorité"
    else:
        titre = "Stock"
    carte: dict[str, Any] = {"type": "stock", "titre": titre, "items": items}
    urgents = [i for i in items if i["sous_seuil"] and i["fournisseur"]]
    if urgents:
        plus_urgent = min(urgents, key=lambda i: i["niveau"] if i["niveau"] is not None else 0)
        carte["action"] = {
            "libelle": "Préparer la commande",
            "message": f"Prépare une commande de {plus_urgent['ingredient']} chez {plus_urgent['fournisseur']}",
        }
    return carte


def _ventes(data: dict) -> dict | None:
    if not data.get("par_produit"):
        return None
    periode = data["periode"]
    return {
        "type": "ventes",
        "titre": f"Ventes du {_jj_mm(periode['debut'])} au {_jj_mm(periode['fin'])}",
        "total_quantite": data["total_quantite"],
        "total_ca": data["total_ca"],
        "barres": _barres([(p["produit"], p["quantite"]) for p in data["par_produit"]]),
    }


def _marge(data: dict) -> dict | None:
    items = [
        {k: p[k] for k in ("produit", "prix_vente_ttc", "cout_revient", "marge_unitaire", "marge_pct")}
        for p in data.get("items", [])[:3]
    ]
    if not items:
        return None
    titre = f"Marge · {items[0]['produit']}" if len(items) == 1 else "Marges"
    return {"type": "marge", "titre": titre, "items": items}


def _prevision(data: dict, status: str) -> dict | None:
    produits = data.get("produits", [])
    if not produits:
        return None
    premier = produits[0]
    return {
        "type": "prevision",
        "titre": f"Prévision · {data['jour']} {_jj_mm(data['date_cible'])}",
        "principal": {
            "produit": premier["produit"],
            "recommandation": premier["recommandation"],
            "observations": premier["observations"],
        },
        "barres": _barres([(p["produit"], p["recommandation"]) for p in produits]),
        "fragile": status == "warning",
    }


def _commande(enveloppe: dict) -> dict | None:
    reference = (enveloppe.get("artifacts") or {}).get("reference")
    if not reference:
        return None
    data = enveloppe.get("data", {})
    return {
        "type": "commande",
        "reference": reference,
        "fournisseur": data.get("fournisseur"),
        "destinataire": data.get("destinataire"),
        "partielle": (enveloppe.get("error") or {}).get("code") == "COMMANDE_NON_TRACEE",
    }


def _carte(resultat: ResultatOutil) -> dict | None:
    enveloppe = resultat.enveloppe
    status, data = enveloppe.get("status"), enveloppe.get("data") or {}
    if resultat.outil == "passer_commande":
        return _commande(enveloppe)
    if status not in {"success", "warning"}:
        return None
    if resultat.outil == "prevoir_production":
        return _prevision(data, status)
    if resultat.outil == "consulter_boulangerie":
        if "par_produit" in data:
            return _ventes(data)
        items = data.get("items") or []
        if items and "ingredient" in items[0]:
            return _stock(data)
        if items and "produit" in items[0]:
            return _marge(data)
    return None


def cartes_depuis(resultats: list[ResultatOutil]) -> list[dict]:
    """Une carte par résultat utile, dans l'ordre des appels (3 au plus).

    Après une commande, seule sa confirmation est montrée : les lectures qui
    l'ont préparée (recherche du fournisseur) n'apporteraient que du bruit."""
    cartes = [carte for carte in map(_carte, resultats) if carte]
    commandes = [c for c in cartes if c["type"] == "commande"]
    return (commandes or cartes)[:3]
