import os
from typing import Optional
from notion_client import Client
from langchain.tools import tool
from datetime import datetime


# Connexion Notion
notion_client = Client(auth=os.getenv("NOTION_TOKEN"))
STOCK_DB_ID = os.getenv("STOCK_DB_ID")
VENTES_DB_ID = os.getenv("VENTES_DB_ID")
CATALOGUE_DB_ID = os.getenv("CATALOGUE_DB_ID")
COMMANDES_DB_ID = os.getenv("COMMANDES_DB_ID")

def _get_data_source_id(database_id: str) -> str:
    """Récupère le data_source_id depuis un database_id Notion."""
    response = notion_client.databases.retrieve(database_id=database_id)
    return response["data_sources"][0]["id"]


@tool
def lire_stock(ingredient_name: str) -> str:
    """Consulte le stock d'ingrédients de la boulangerie.

    QUAND L'UTILISER :
    - Question sur un stock : "combien de beurre", "reste de farine"
    - Question sur un fournisseur : "qui fournit le beurre", "email Dupont"
    - Question sur un seuil d'alerte : "faut commander ?"

    QUAND NE PAS UTILISER :
    - Pour les ventes ou le chiffre d'affaires
    - Pour les prix de vente ou les marges
    - Pour envoyer une commande ou faire une prévision

    PARAMETRE :
    - ingredient_name : nom ou mot-clé de l'ingrédient recherché. Ex : "beurre", "farine T65", "levure"
    """
    print(f"[TOOL CALL] lire_stock | ingredient_name={ingredient_name}")
    try:
        data_source_id = _get_data_source_id(STOCK_DB_ID)
        database = notion_client.data_sources.query(
            data_source_id=data_source_id,
            filter={"property": "Ingrédient", "title": {"contains": ingredient_name}}
        )
    except Exception as e:
        return f"Erreur lors de la consultation du stock : {e}"

    if not database["results"]:
        return f"Aucun ingrédient trouvé pour '{ingredient_name}'."

    final_text = "Stock actuel :\n"
    for item in database["results"]:
        nom = item["properties"]["Ingrédient"]["title"][0]["plain_text"]
        quantite = item["properties"]["Quantité en stock"]["number"]
        
        unite_info = item["properties"]["Unité"]["select"]
        unite = unite_info["name"] if unite_info else ""
        
        fourn_info = item["properties"]["Fournisseur"]["select"]
        fournisseur = fourn_info["name"] if fourn_info else "Non spécifié"
        
        email = item["properties"]["Email fournisseur"]["email"] or "Pas d'email"
        seuil = item["properties"]["Seuil alerte"]["number"] or 0
        
        date_info = item["properties"]["Dernière livraison"]["date"]
        livraison = date_info["start"] if date_info else "Inconnue"

        final_text += (
            f"- {nom} : {quantite} {unite} | "
            f"Fournisseur : {fournisseur} ({email}) | "
            f"Seuil d'alerte : {seuil} {unite} | "
            f"Dernière livraison : {livraison}\n"
        )

    return final_text


@tool
def lire_ventes(product_name: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """Consulte l'historique des ventes de la boulangerie.

    QUAND L'UTILISER :
    - Question sur les ventes d'un produit : "combien de croissants j'ai vendu"
    - Question sur le chiffre d'affaires : "quel est mon CA", "combien j'ai gagné"
    - Question sur une période : "la semaine dernière", "hier", "entre telle date et telle date"
    - Question de comparaison de ventes : "quel produit s'est le mieux vendu", "les ventes de baguettes"

    QUAND NE PAS UTILISER :
    - Pour consulter le stock d'ingrédients ou les seuils d'alerte
    - Pour trouver un fournisseur ou un email fournisseur
    - Pour envoyer une commande fournisseur
    - Pour consulter les recettes ou les ingrédients d'un produit

    PARAMÈTRES :
    - product_name : nom du produit recherché.
      OPTIONS DISPONIBLES : "Baguette tradition", "Pain de campagne", "Croissant pur beurre",
      "Pain au chocolat", "Chausson aux pommes", "Brioche tressée", "Tarte citron meringuée",
      "Éclair au chocolat", "Flan pâtissier", "Croque-monsieur", "Quiche lorraine", "Pain complet"
    - start_date : date de début au format YYYY-MM-DD
    - end_date : date de fin au format YYYY-MM-DD
    """
    print(f"[TOOL CALL] lire_ventes | product_name={product_name} | start_date={start_date} | end_date={end_date}")
    if not start_date or not end_date:
        return "Merci de préciser la période souhaitée (ex : 'la semaine dernière', 'du 1er au 7 juin')."

    total_ca = 0
    total_quantite = 0
    
    if product_name:
        final_text = f"Ventes de '{product_name}' entre {start_date} et {end_date} :\n"
    else:
        final_text = f"Ventes globales entre {start_date} et {end_date} :\n"
        
    try:
        data_source_id = _get_data_source_id(VENTES_DB_ID)
        filters = []
        if product_name:
            filters.append({"property": "Produit", "select": {"equals": product_name}})
        if start_date:
            filters.append({"property": "Date", "date": {"on_or_after": start_date}})
        if end_date:
            filters.append({"property": "Date", "date": {"on_or_before": end_date}})
        filter_query = {"and": filters} if filters else None

        response = notion_client.data_sources.query(
            data_source_id=data_source_id,
            filter=filter_query
        )
    except Exception as e :
        return f"Erreur lors de la consultation des ventes : {e}"
        
    if not response["results"]:
        target_name = f"'{product_name}'" if product_name else "tous les produits"
        return f"Aucune vente trouvée pour {target_name} entre {start_date} et {end_date}."
        
    for item in response["results"]:
        prod_info = item["properties"]["Produit"]["select"]
        produit = prod_info["name"] if prod_info else "Produit inconnu"
        quantite = item["properties"]["Quantité vendue"]["number"] or 0
        ca = item["properties"]["CA (€)"]["number"] or 0.0
        
        date_info = item["properties"]["Date"]["date"]
        date = date_info["start"] if date_info else "Date inconnue"
        
        total_ca += ca
        total_quantite += quantite
        
        final_text += f"- {date} : {quantite}x {produit} (CA : {ca} €)\n"
        
    final_text += f"\nTOTAL : {total_quantite} produit(s) vendu(s) pour un CA global de {total_ca} €"
    return final_text

@tool
def lire_catalogue(product_name:str)->str:
    """Consulte les informations d'un produit du catalogue.

    À utiliser pour les questions sur un produit précis :
    prix de vente, coût de revient, marge, ingrédients principaux,
    temps de préparation, catégorie ou disponibilité.

    Ne pas utiliser pour :
    - les stocks d'ingrédients
    - les ventes historiques
    - le chiffre d'affaires sur une période
    - les commandes fournisseurs
    - les comparaisons entre plusieurs produits

    Paramètre :
    product_name : nom ou mot-clé du produit recherché.
    Exemples : "croissant", "éclair au chocolat", "baguette tradition".
    """
    print(f"[TOOL CALL] lire_catalogue | product_name={product_name}")
    try:
        data_source_id = _get_data_source_id(CATALOGUE_DB_ID)
        filter_query = {"property": "Produit", "title": {"contains": product_name}}
        response = notion_client.data_sources.query(
            data_source_id=data_source_id,
            filter=filter_query
        )
    except Exception as e:
        return f"Erreur lors de la consultation du catalogue : {e}"
    if not response["results"]:
        return f"Aucun produit trouvé pour '{product_name}'."
    final_text = "Informations sur le produit :\n"
    for item in response["results"]:
        produit = item["properties"]["Produit"]["title"][0]["plain_text"]
        
        cat_info = item["properties"]["Catégorie"]["select"]
        categorie = cat_info["name"] if cat_info else "Non spécifié"
        
        prix_vente = item["properties"]["Prix de vente TTC (€)"]["number"] or 0.0
        cout_revient = item["properties"]["Coût de revient (€)"]["number"] or 0.0
        
        marge_info = item["properties"]["Marge (%)"]["formula"]
        marge = marge_info["number"] if (marge_info and "number" in marge_info) else 0.0
        
        ing_info = item["properties"]["Ingrédients principaux"]["rich_text"]
        ingredients = ing_info[0]["plain_text"] if ing_info else "Aucun"
        
        temps_preparation = item["properties"]["Temps de préparation (min)"]["number"] or 0
        disponible = "Oui" if item["properties"]["Disponible"]["checkbox"] else "Non"
        
        final_text += (
            f"- {produit} ({categorie}) :\n"
            f"  Prix de vente : {prix_vente} € | Coût de revient : {cout_revient} € | Marge : {marge :.1f}%\n"
            f"  Ingrédients principaux : {ingredients}\n"
            f"  Temps de préparation : {temps_preparation} min | Disponible : {disponible}\n"
        )
        
    return final_text
        
@tool
def enregistrer_commande(
    fournisseur: str,
    email_fournisseur: str,
    produits: str,
    montant_estime: float = 0.0,
    notes: str = ""
) -> str:
    """Enregistre une commande fournisseur dans Notion.
    
    IMPORTANT : Utiliser lire_stock() en premier pour obtenir
    le nom et l'email du fournisseur si non connus.

    À UTILISER :
    - Immédiatement après avoir passé/envoyé une commande de matières premières à un fournisseur.

    PARAMÈTRES :
    - fournisseur : nom du fournisseur (ex: "Laiterie du Midi")
    - email_fournisseur : adresse e-mail de destination (ex: "pro@laiterie-du-midi.fr")
    - produits : description des produits et quantités (ex: "10 kg de Beurre AOP")
    - montant_estime : coût total estimé (ex: 66.0)
    - notes : informations ou consignes supplémentaires (ex: "Livraison le matin")
    """
    print(f"[TOOL CALL] enregistrer_commande | fournisseur={fournisseur} | email_fournisseur={email_fournisseur} | produits={produits} | montant_estime={montant_estime} | notes={notes}")
    try:
        # 1. On génère une référence simple (ex: CMD-20260621-LAIT)
        date_str = datetime.now().strftime("%Y%m%d")
        ref_commande = f"CMD-{date_str}-{fournisseur.upper()[:4]}"

        # 2. Date du jour au format ISO (YYYY-MM-DD) requis par Notion
        date_du_jour = datetime.now().date().isoformat()

        # 3. Écriture dans Notion
        response = notion_client.pages.create(
            parent={"database_id": COMMANDES_DB_ID},
            properties={
                "Référence commande": {
                    "title": [
                        {
                            "text": {
                                "content": ref_commande
                            }
                        }
                    ]
                },
                "Date commande": {
                    "date": {
                        "start": date_du_jour
                    }
                },
                "Email envoyé à": {
                    "email": email_fournisseur
                },
                "Fournisseur": {
                    "select": {
                        "name": fournisseur
                    }
                },
                "Montant estimé (€)": {
                    "number": montant_estime
                },
                "Notes": {
                    "rich_text": [
                        {
                            "text": {
                                "content": notes
                            }
                        }
                    ]
                },
                "Produits commandés": {
                    "rich_text": [
                        {
                            "text": {
                                "content": produits
                            }
                        }
                    ]
                },
                "Statut": {
                    "select": {
                        "name": "Envoyée"
                    }
                }
            }
        )
        return f"Commande enregistrée avec succès dans Notion sous la référence {ref_commande}."

    except Exception as e:
        return f"Erreur lors de l'enregistrement de la commande : {e}"

