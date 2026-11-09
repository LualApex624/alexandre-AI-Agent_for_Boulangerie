"""Les trois outils d'Alexandre. Contrat détaillé : docs/tools.md."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Protocol

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, ValidationError

from boulangerie.envelope import arrondi, avertissement, detail_erreur, erreur, notion_indisponible, succes
from boulangerie.forecast import COEFFICIENT, OBSERVATIONS_MINIMALES, fenetre, prevoir
from boulangerie.notion_repo import Ingredient, NotionIndisponible, NotionRepository, NouvelleCommande
from boulangerie.prompt import jour_fr

log = logging.getLogger(__name__)


class Mailer(Protocol):
    async def envoyer(self, destinataire: str, objet: str, corps: str) -> None: ...


@dataclass
class Deps:
    repo: NotionRepository
    mailer: Mailer | None
    trace_dir: Path
    clock: Callable[[], datetime] = field(default=datetime.now)


def normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in sans_accents if not unicodedata.combining(c)).casefold().strip()


def correspond(recherche: str | None, nom: str) -> bool:
    if not recherche:
        return True
    cible, mot = normaliser(nom), normaliser(recherche)
    singulier = mot[:-1] if len(mot) > 3 and mot.endswith("s") else mot
    return mot in cible or singulier in cible


# --- Outil 1 : consulter_boulangerie -------------------------------------------

class ConsulterArgs(BaseModel):
    table: Literal["stock", "ventes", "catalogue"] = Field(
        description="stock = ingrédients, seuils, fournisseurs ; ventes = quantités vendues et chiffre "
        "d'affaires ; catalogue = prix, coût, marge, ingrédients, temps de préparation des produits."
    )
    recherche: str | None = Field(
        default=None,
        description="Mot-clé court sur le nom de l'ingrédient ou du produit (ex. 'beurre', 'croissant'). "
        "Laisser vide pour tout lister.",
    )
    date_debut: date | None = Field(
        default=None, description="Début de période AAAA-MM-JJ. Obligatoire pour table='ventes'."
    )
    date_fin: date | None = Field(
        default=None, description="Fin de période AAAA-MM-JJ (incluse). Obligatoire pour table='ventes'."
    )
    sous_seuil_uniquement: bool = Field(
        default=False,
        description="table='stock' uniquement : ne garder que les ingrédients à commander "
        "(quantité inférieure ou égale au seuil d'alerte).",
    )


def _aucune_correspondance(quoi: str, ce_quoi: str, recherche: str | None, data: dict) -> str:
    return avertissement(
        f"Aucun {quoi} ne correspond à « {recherche} ».",
        data,
        next_actions=[
            "Réessaie une fois avec un mot-clé plus court.",
            f"Sinon, dis à Madeleine que tu ne trouves pas {ce_quoi}.",
        ],
    )


def _parametre_invalide(cause: str) -> str:
    return erreur(
        "PARAMETRE_INVALIDE",
        "La demande n'est pas valide.",
        cause=cause,
        retry="Corrige l'appel une seule fois.",
        stop="Si tu ne sais pas comment corriger, demande une précision à Madeleine.",
    )


async def _consulter_stock(deps: Deps, recherche: str | None, sous_seuil_uniquement: bool) -> str:
    ingredients = [i for i in await deps.repo.lister_stock() if correspond(recherche, i.nom)]
    if recherche and not ingredients:
        return _aucune_correspondance("ingrédient", "cet ingrédient", recherche, {"items": [], "nb_resultats": 0})
    if sous_seuil_uniquement:
        ingredients = sorted(
            (i for i in ingredients if i.sous_seuil),
            key=lambda i: (i.quantite / i.seuil) if i.seuil else 0,
        )
    items = [
        {
            "ingredient": i.nom,
            "quantite": arrondi(i.quantite),
            "unite": i.unite,
            "seuil_alerte": arrondi(i.seuil),
            "sous_seuil": i.sous_seuil,
            "fournisseur": i.fournisseur,
            "email_fournisseur": i.email,
            "prix_unitaire": arrondi(i.prix_unitaire),
            "derniere_livraison": i.derniere_livraison,
        }
        for i in ingredients
    ]
    data = {"items": items, "nb_resultats": len(items)}
    if not items:
        return succes("Aucun ingrédient n'est sous son seuil d'alerte.", data)
    alertes = sum(1 for i in items if i["sous_seuil"])
    return succes(f"{len(items)} ingrédient(s) trouvé(s), dont {alertes} sous le seuil d'alerte.", data)


async def _consulter_ventes(deps: Deps, recherche: str | None, debut: date, fin: date) -> str:
    toutes = await deps.repo.lister_ventes()
    disponibles = (
        {"debut": min(v.jour for v in toutes).isoformat(), "fin": max(v.jour for v in toutes).isoformat()}
        if toutes
        else None
    )
    retenues = [v for v in toutes if debut <= v.jour <= fin and correspond(recherche, v.produit)]
    cumuls: dict[str, dict[str, float]] = {}
    for v in retenues:
        cumul = cumuls.setdefault(v.produit, {"quantite": 0.0, "ca": 0.0})
        cumul["quantite"] += v.quantite
        cumul["ca"] += v.ca
    par_produit = [
        {"produit": produit, "quantite": arrondi(c["quantite"]), "ca": arrondi(c["ca"])}
        for produit, c in sorted(cumuls.items(), key=lambda kv: -kv[1]["quantite"])
    ]
    data = {
        "periode": {"debut": debut.isoformat(), "fin": fin.isoformat()},
        "par_produit": par_produit,
        "total_quantite": arrondi(sum(v.quantite for v in retenues)) or 0,
        "total_ca": arrondi(sum(v.ca for v in retenues)) or 0,
        "nb_lignes": len(retenues),
        "donnees_disponibles": disponibles,
    }
    if not retenues:
        couverture = (
            f"Les ventes enregistrées vont du {disponibles['debut']} au {disponibles['fin']}."
            if disponibles
            else "Aucune vente n'est enregistrée."
        )
        return avertissement(
            f"Aucune vente trouvée du {debut} au {fin}. {couverture}",
            data,
            next_actions=["Dis à Madeleine qu'il n'y a pas de ventes enregistrées pour cette période."],
        )
    resume = f"{data['total_quantite']} article(s) vendu(s) pour {data['total_ca']} € du {debut} au {fin}."
    if disponibles and (debut.isoformat() < disponibles["debut"] or fin.isoformat() > disponibles["fin"]):
        resume += f" Attention : les données ne couvrent que du {disponibles['debut']} au {disponibles['fin']}."
    return succes(resume, data)


async def _consulter_catalogue(deps: Deps, recherche: str | None) -> str:
    produits = [p for p in await deps.repo.lister_catalogue() if correspond(recherche, p.nom)]
    items = [
        {
            "produit": p.nom,
            "categorie": p.categorie,
            "prix_vente_ttc": arrondi(p.prix),
            "cout_revient": arrondi(p.cout),
            "marge_unitaire": arrondi(p.prix - p.cout) if p.prix is not None and p.cout is not None else None,
            "marge_pct": arrondi(p.marge_pct),
            "ingredients": p.ingredients,
            "temps_preparation_min": arrondi(p.temps_preparation),
            "disponible": p.disponible,
        }
        for p in produits
    ]
    data = {"items": items, "nb_resultats": len(items)}
    if not items:
        return _aucune_correspondance("produit", "ce produit", recherche, data)
    return succes(f"{len(items)} produit(s) trouvé(s) dans le catalogue.", data)


# --- Outil 3 : prevoir_production ----------------------------------------------

class PrevoirArgs(BaseModel):
    date_cible: date = Field(
        description="Jour à préparer, AAAA-MM-JJ. Convertis « demain » avec le calendrier du prompt."
    )
    produit: str | None = Field(
        default=None, description="Mot-clé du produit (ex. 'baguette'). Laisser vide pour tous les produits."
    )
    fenetre_jours: int = Field(
        default=28, ge=7, le=90, description="Nombre de jours d'historique pris en compte avant la date cible."
    )


async def _prevoir_production(deps: Deps, date_cible: date, produit: str | None, fenetre_jours: int) -> str:
    ventes = [v for v in await deps.repo.lister_ventes() if correspond(produit, v.produit)]
    lignes = prevoir(ventes, date_cible, fenetre_jours)
    debut, fin = fenetre(date_cible, fenetre_jours)
    jour = jour_fr(date_cible)
    data = {
        "date_cible": date_cible.isoformat(),
        "jour": jour,
        "fenetre": {"debut": debut.isoformat(), "fin": fin.isoformat()},
        "coefficient": COEFFICIENT,
        "produits": [
            {
                "produit": ligne.produit,
                "observations": ligne.observations,
                "moyenne": arrondi(ligne.moyenne),
                "recommandation": ligne.recommandation,
            }
            for ligne in lignes
        ],
    }
    if not lignes:
        return avertissement(
            f"Aucune vente un {jour} entre le {debut} et le {fin} : pas de prévision possible.",
            data,
            next_actions=["Dis à Madeleine qu'il n'y a pas d'historique pour ce jour ; ne propose aucune quantité."],
        )
    if any(ligne.observations < OBSERVATIONS_MINIMALES for ligne in lignes):
        return avertissement(
            f"Prévision pour le {jour} {date_cible} calculée sur peu de {jour}s "
            f"(moins de {OBSERVATIONS_MINIMALES} observations) : estimation fragile.",
            data,
            next_actions=["Donne les recommandations en précisant que l'estimation est fragile."],
        )
    return succes(f"Prévision pour le {jour} {date_cible} : moyenne des {jour}s + 10 %.", data)


# --- Outil 2 : passer_commande -------------------------------------------------

OBJET_MAX = 150
CORPS_MAX = 3000
FOURNISSEUR_MAX = 100
PRODUITS_MAX = 500
# Jeton posé par Conversation.valider uniquement quand Madeleine a cliqué « Envoyer ».
CLE_VALIDATION = "validation_madeleine"
EMAIL_SIMPLE = re.compile(r"^[^@\s,;<>\"']+@[^@\s,;<>\"']+\.[A-Za-z]{2,}$")
FICHIER_TRACE = "commandes_non_tracees.jsonl"


class CommanderArgs(BaseModel):
    fournisseur: str = Field(description="Nom du fournisseur tel qu'il apparaît dans le stock (ex. 'Minoterie Dupont').")
    produits: str = Field(description="Produits et quantités commandés, ex. '50 kg de Farine T65'.")
    objet: str = Field(description=f"Objet de l'email, une seule ligne, {OBJET_MAX} caractères maximum.")
    corps: str = Field(description="Corps de l'email en texte brut (pas de markdown), signé par Madeleine.")
    montant_estime: float | None = Field(
        default=None,
        description="Montant estimé en euros : quantités × prix unitaires lus dans le stock. Laisser vide sinon.",
    )


@dataclass(frozen=True)
class Fournisseur:
    nom: str  # nom canonique, tel qu'écrit dans le stock
    email: str | None


def fournisseurs(stock: list[Ingredient]) -> dict[str, Fournisseur]:
    """Annuaire des fournisseurs (clé : nom normalisé) d'après les fiches du stock."""
    annuaire: dict[str, Fournisseur] = {}
    for ingredient in stock:
        if ingredient.fournisseur:
            cle = normaliser(ingredient.fournisseur)
            connu = annuaire.get(cle, Fournisseur(ingredient.fournisseur, None))
            annuaire[cle] = Fournisseur(connu.nom, connu.email or ingredient.email)
    return annuaire


def trouver_fournisseur(stock: list[Ingredient], nom: str) -> Fournisseur | None:
    return fournisseurs(stock).get(normaliser(nom))


def _valider_commande(
    fournisseur: str, objet: str, corps: str, produits: str, montant: float | None
) -> str | None:
    if not fournisseur.strip() or len(fournisseur) > FOURNISSEUR_MAX:
        return f"Le fournisseur doit faire entre 1 et {FOURNISSEUR_MAX} caractères."
    if len(produits) > PRODUITS_MAX:
        return f"La liste des produits ne doit pas dépasser {PRODUITS_MAX} caractères."
    if not objet.strip() or len(objet) > OBJET_MAX:
        return f"L'objet doit faire entre 1 et {OBJET_MAX} caractères."
    if "\r" in objet or "\n" in objet:
        return "L'objet doit tenir sur une seule ligne."
    if not corps.strip() or len(corps) > CORPS_MAX:
        return f"Le corps doit faire entre 1 et {CORPS_MAX} caractères."
    if not produits.strip():
        return "Il faut préciser les produits et quantités."
    if montant is not None and montant < 0:
        return "Le montant estimé ne peut pas être négatif."
    return None


def _tracer_localement(deps: Deps, commande: NouvelleCommande, cause: str) -> Path:
    # Contient des données de commande : dossier et fichier réservés au propriétaire.
    deps.trace_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(deps.trace_dir, 0o700)
    chemin = deps.trace_dir / FICHIER_TRACE
    enregistrement = {
        "horodatage": deps.clock().isoformat(timespec="seconds"),
        "cause": cause,
        **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in asdict(commande).items()},
    }
    descripteur = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.chmod(chemin, 0o600)
    with os.fdopen(descripteur, "a", encoding="utf-8") as fichier:
        fichier.write(json.dumps(enregistrement, ensure_ascii=False) + "\n")
    return chemin


async def _passer_commande(
    deps: Deps,
    fournisseur: str,
    produits: str,
    objet: str,
    corps: str,
    montant_estime: float | None,
    validee: bool,
) -> str:
    if not validee:
        return erreur(
            "VALIDATION_REQUISE",
            "Madeleine n'a pas validé cet envoi : rien n'a été envoyé ni noté.",
            cause="L'outil a été appelé sans la validation explicite de Madeleine.",
            retry="Ne réessaie pas de toi-même.",
            stop="Demande à Madeleine si elle veut envoyer cette commande.",
        )
    probleme = _valider_commande(fournisseur, objet, corps, produits, montant_estime)
    if probleme:
        return _parametre_invalide(probleme)
    if deps.mailer is None:
        return erreur(
            "EMAIL_NON_CONFIGURE",
            "L'envoi d'emails n'est pas configuré : rien n'a été envoyé ni noté.",
            cause="Aucun serveur d'envoi d'emails n'est renseigné.",
            retry="Ne réessaie pas.",
            stop="Dis à Madeleine que l'envoi d'emails n'est pas encore branché et propose de lui donner le texte du mail.",
        )

    try:
        stock = await deps.repo.lister_stock()
    except NotionIndisponible:
        return notion_indisponible()
    trouve = trouver_fournisseur(stock, fournisseur)
    if trouve is None:
        return erreur(
            "FOURNISSEUR_INCONNU",
            f"« {fournisseur} » n'est pas un fournisseur connu : rien n'a été envoyé.",
            cause="Ce nom ne correspond à aucun fournisseur du stock.",
            retry="Reprends la commande avec un des noms de data.fournisseurs_connus.",
            stop="Si aucun ne convient, demande à Madeleine de préciser le fournisseur.",
            data={"fournisseurs_connus": sorted({f.nom for f in fournisseurs(stock).values()}, key=normaliser)},
        )
    nom_fournisseur, email = trouve.nom, trouve.email
    if not email or not EMAIL_SIMPLE.fullmatch(email):
        return erreur(
            "FOURNISSEUR_SANS_EMAIL",
            f"Pas d'adresse email valide enregistrée pour {nom_fournisseur} : rien n'a été envoyé.",
            cause="L'email du fournisseur est vide ou invalide dans le stock.",
            retry="Ne réessaie pas.",
            stop="Dis à Madeleine qu'il faut ajouter l'email de ce fournisseur dans ses fiches.",
        )

    try:
        await deps.mailer.envoyer(email, objet, corps)
    except Exception as exc:  # noqa: BLE001 — aucune erreur SMTP ne doit remonter vers l'interface
        log.warning("Échec d'envoi de l'email à %s : %s", nom_fournisseur, type(exc).__name__)
        return erreur(
            "EMAIL_ECHEC",
            "L'email n'a pas pu partir : rien n'a été envoyé ni noté.",
            cause="Le serveur d'envoi d'emails a refusé ou n'a pas répondu.",
            retry="Ne réessaie pas de toi-même.",
            stop="Préviens Madeleine que l'email n'est pas parti et propose de réessayer plus tard.",
        )

    commande = NouvelleCommande(
        reference=f"CMD-{deps.clock():%Y%m%d}-{secrets.token_hex(2).upper()}",
        jour=deps.clock().date(),
        fournisseur=nom_fournisseur,
        email=email,
        produits=produits,
        montant_estime=montant_estime,
        corps=corps,
    )
    try:
        page_id = await deps.repo.creer_commande(commande)
    except NotionIndisponible:
        chemin = _tracer_localement(deps, commande, "écriture Notion impossible après envoi de l'email")
        return avertissement(
            f"L'email est parti chez {nom_fournisseur}, mais la commande {commande.reference} "
            "n'a pas pu être notée dans les commandes. Elle est gardée de côté.",
            {"destinataire": email, "fournisseur": nom_fournisseur, "objet": objet},
            next_actions=["Explique à Madeleine que l'email est bien parti et que la commande est gardée de côté."],
            artifacts={"reference": commande.reference, "trace_locale": str(chemin)},
            error=detail_erreur(
                "COMMANDE_NON_TRACEE",
                cause="L'enregistrement de la commande a échoué après l'envoi de l'email.",
                retry="Ne jamais relancer passer_commande : l'email partirait une deuxième fois.",
                stop="Arrête-toi là et informe Madeleine.",
            ),
        )
    return succes(
        f"Email envoyé à {nom_fournisseur} et commande {commande.reference} enregistrée.",
        {"destinataire": email, "fournisseur": nom_fournisseur, "objet": objet},
        artifacts={"reference": commande.reference, "notion_page_id": page_id},
    )


def _argument_invalide(exc: ValidationError) -> str:
    """Argument hors schéma (type, borne, valeur non prévue) : enveloppe, jamais d'exception."""
    champs = ", ".join(sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()}))
    return _parametre_invalide(f"Argument invalide : {champs}. Vérifie les valeurs autorisées dans la description.")


def build_tools(deps: Deps) -> list[BaseTool]:
    async def consulter_boulangerie(
        table: str,
        recherche: str | None = None,
        date_debut: date | None = None,
        date_fin: date | None = None,
        sous_seuil_uniquement: bool = False,
    ) -> str:
        if sous_seuil_uniquement and table != "stock":
            return _parametre_invalide("sous_seuil_uniquement ne s'applique qu'à table='stock'.")
        try:
            if table == "stock":
                return await _consulter_stock(deps, recherche, sous_seuil_uniquement)
            if table == "catalogue":
                return await _consulter_catalogue(deps, recherche)
            # table == "ventes" (le schéma n'admet que ces trois valeurs)
            if date_debut is None or date_fin is None:
                return erreur(
                    "PERIODE_MANQUANTE",
                    "Il faut une période (date de début et de fin) pour lire les ventes.",
                    cause="date_debut ou date_fin est absente.",
                    retry="Ne réessaie pas avec des dates inventées.",
                    stop="Demande à Madeleine de quelle période elle parle.",
                )
            if date_debut > date_fin:
                return _parametre_invalide("date_debut est après date_fin.")
            return await _consulter_ventes(deps, recherche, date_debut, date_fin)
        except NotionIndisponible:
            return notion_indisponible()

    async def prevoir_production(date_cible: date, produit: str | None = None, fenetre_jours: int = 28) -> str:
        try:
            return await _prevoir_production(deps, date_cible, produit, fenetre_jours)
        except NotionIndisponible:
            return notion_indisponible()

    async def passer_commande(
        fournisseur: str,
        produits: str,
        objet: str,
        corps: str,
        montant_estime: float | None = None,
        *,
        config: RunnableConfig,
    ) -> str:
        validee = (config.get("configurable") or {}).get(CLE_VALIDATION) is True
        return await _passer_commande(deps, fournisseur, produits, objet, corps, montant_estime, validee)

    return [
        StructuredTool.from_function(
            coroutine=consulter_boulangerie,
            name="consulter_boulangerie",
            description=(
                "Lit les données de la boulangerie : stock d'ingrédients (quantités, seuils d'alerte, "
                "fournisseurs), ventes sur une période (quantités, chiffre d'affaires) ou catalogue "
                "des produits (prix, coût de revient, marge). Seule source autorisée pour ces chiffres."
            ),
            args_schema=ConsulterArgs,
            handle_validation_error=_argument_invalide,
        ),
        StructuredTool.from_function(
            coroutine=prevoir_production,
            name="prevoir_production",
            description=(
                "Estime combien préparer de chaque produit pour un jour donné : moyenne des ventes du "
                "même jour de la semaine sur l'historique, plus 10 % de marge de sécurité."
            ),
            args_schema=PrevoirArgs,
            handle_validation_error=_argument_invalide,
        ),
        StructuredTool.from_function(
            coroutine=passer_commande,
            name="passer_commande",
            description=(
                "Envoie l'email de commande au fournisseur (adresse lue dans le stock) puis enregistre la "
                "commande. Action irréversible : Madeleine valide le brouillon avant l'exécution."
            ),
            args_schema=CommanderArgs,
            handle_validation_error=_argument_invalide,
        ),
    ]
