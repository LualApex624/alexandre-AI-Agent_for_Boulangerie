"""Envoi SMTP réel (STARTTLS), exécuté hors de la boucle d'événements."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from boulangerie.config import SmtpSettings

TIMEOUT_SECONDES = 20


class EnTeteInvalide(ValueError):
    """Un en-tête contient un retour à la ligne (tentative d'injection d'en-tête)."""


def _verifier_en_tete(valeur: str) -> str:
    if "\r" in valeur or "\n" in valeur:
        raise EnTeteInvalide("retour à la ligne interdit dans un en-tête")
    return valeur


class SmtpMailer:
    def __init__(self, settings: SmtpSettings):
        self._settings = settings

    def _envoyer_sync(self, destinataire: str, objet: str, corps: str) -> None:
        message = EmailMessage()
        message["From"] = _verifier_en_tete(self._settings.from_address)
        message["To"] = _verifier_en_tete(destinataire)
        message["Subject"] = _verifier_en_tete(objet)
        message.set_content(corps)
        with smtplib.SMTP(self._settings.host, self._settings.port, timeout=TIMEOUT_SECONDES) as smtp:
            smtp.starttls()
            smtp.login(self._settings.user, self._settings.password)
            smtp.send_message(message)

    async def envoyer(self, destinataire: str, objet: str, corps: str) -> None:
        await asyncio.to_thread(self._envoyer_sync, destinataire, objet, corps)
