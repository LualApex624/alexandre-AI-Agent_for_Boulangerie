import pandas as pd 
from langchain.tools import tool
from tools.notion import notion_client, _get_data_source_id, VENTES_DB_ID


def _get_historique_ventes() -> list:
    data_source_id = _get_data_source_id(VENTES_DB_ID)
    response = notion_client.data_sources.query(
        data_source_id=data_source_id
    )
    return response["results"]

@tool
def prevision_production(jour_semaine: str) -> str:
    """Calcule les prévisions de production pour un jour de la semaine donné.

Analyse l'historique des ventes pour ce jour, calcule la moyenne par produit,
et ajoute 10% de marge de sécurité.

QUAND L'UTILISER :
- "Qu'est-ce que je prépare demain ?"
- "Combien de baguettes je fais mercredi ?"
- "Prévision pour samedi"

QUAND NE PAS UTILISER :
- Pour consulter les stocks ou les ventes passées
- Pour envoyer une commande fournisseur
- Pour des questions sur les prix ou les marges

PARAMÈTRE :
- jour_semaine : jour en français avec majuscule.
  OPTIONS : "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"
"""
    try:
        results = _get_historique_ventes()
    except Exception as e:
        return f"Erreur lors de la récupération des ventes : {e}"
    
    # 1. On extrait proprement les données imbriquées de Notion
    cleaned_data = []
    for row in results:
        properties = row.get("properties", {})
        
        # Extraction du nom du produit
        produit_info = properties.get("Produit", {}).get("select", {})
        produit = produit_info.get("name", "") if produit_info else ""
        
        # Extraction de la quantité vendue
        quantite = properties.get("Quantité vendue", {}).get("number", 0)
        
        # Extraction de la date
        date_obj = properties.get("Date", {}).get("date", {})
        date_str = date_obj.get("start", "") if date_obj else ""
        
        if produit and quantite is not None and date_str:
            # On convertit la date pour trouver le jour de la semaine en français
            try:
                dt = pd.to_datetime(date_str)
                # Dictionnaire de traduction des jours
                jours_trad = {
                    "Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi",
                    "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi",
                    "Sunday": "Dimanche"
                }
                nom_jour = jours_trad.get(dt.strftime("%A"), "")
                
                cleaned_data.append({
                    "Produit": produit,
                    "Quantite": quantite,
                    "Jour": nom_jour
                })
            except Exception:
                continue

    if not cleaned_data:
        return "Aucune donnée de vente disponible pour effectuer une prévision."

    # 2. Création du DataFrame Pandas
    df = pd.DataFrame(cleaned_data)
    
    # 3. Filtrage sur le jour de la semaine demandé
    df_jour = df[df["Jour"] == jour_semaine]
    
    if df_jour.empty:
        return f"Aucun historique de vente trouvé pour les jours suivants : {jour_semaine}."
        
    # 4. Calcul de la moyenne par produit avec une marge de 10%
    # On arrondit à l'unité supérieure ou la plus proche pour avoir des pièces entières
    moyennes = df_jour.groupby("Produit")["Quantite"].mean() * 1.1
    
    # 5. Formatage du message de retour
    ret = f"Prévisions de production pour le {jour_semaine} (Moyenne historique + 10% de marge) :\n"
    for produit, quantite_prevue in moyennes.items():
        ret += f"- {produit} : {round(quantite_prevue)} unités\n"
        
    return ret

    