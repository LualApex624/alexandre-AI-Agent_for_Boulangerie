import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv()

EMAIL_HOST = os.getenv("SMTP_HOST")
EMAIL_PORT = int(os.getenv("SMTP_PORT"))
EMAIL_USER = os.getenv("SMTP_USER")
EMAIL_PASS = os.getenv("SMTP_PASS")
EMAIL_FROM = os.getenv("SMTP_FROM")
@tool
def envoyer_email(destinataire: str, objet: str, corps: str) -> str:
    """
    Envoie un email de commande à un fournisseur de la boulangerie.

    QUAND L'UTILISER :
    - Madeleine veut passer une commande à un fournisseur
    - Madeleine veut contacter un fournisseur par email
    - Après confirmation explicite de Madeleine

    QUAND NE PAS UTILISER :
    - Pour consulter les stocks ou les ventes
    - Pour faire une prévision de production
    - Sans confirmation préalable de Madeleine

    PARAMÈTRES :
    - destinataire : email du fournisseur (récupéré depuis le stock Notion)
    - objet : sujet de l'email de commande
    - corps : contenu de l'email rédigé en français professionnel
    FORMAT DU CORPS :
    - Email professionnel en français
    - Maximum 150 mots
    - Inclure : produit, quantité, coordonnées de la boulangerie
    - Commencer par "Madame, Monsieur,"
    - Terminer par "Cordialement, Madeleine Croûton - Boulangerie Chez Madeleine"
    EXEMPLE DE CORPS :
    Madame, Monsieur,

    Je me permets de vous contacter afin de passer commande de 50 kg
    de farine T65. Merci de bien vouloir livrer à notre adresse habituelle.

    Dans l'attente de votre confirmation, je reste disponible.

    Cordialement,
    Madeleine Croûton
    Boulangerie Chez Madeleine - Saint-Germain-des-Croissants
    """
    message=MIMEMultipart()
    message["from"]=EMAIL_FROM
    message["to"]=destinataire
    message["subject"]=objet
    message.attach(MIMEText(corps,"plain"))
    try:
        with smtplib.SMTP(EMAIL_HOST,EMAIL_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USER,EMAIL_PASS)
            smtp.send_message(message)
        return "Email envoyé avec succès"
    except Exception as e:
        return f"Erreur lors de l'envoi de l'email : {e}"