"""Configuration typée, lue une seule fois au démarrage depuis l'environnement.

Les secrets ne vivent que dans les variables d'environnement (fichier `.env`
local, jamais commité). Ils sont exclus de la représentation des objets pour
ne jamais finir dans un log ou un message d'erreur.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REQUIRED = (
    "NOTION_TOKEN",
    "STOCK_DB_ID",
    "VENTES_DB_ID",
    "CATALOGUE_DB_ID",
    "COMMANDES_DB_ID",
    "GOOGLE_API_KEY",
)
SMTP_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM")

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_FALLBACK_MODEL = "mistral-small-latest"
DEFAULT_DATE_REFERENCE = "2026-02-16"


class ConfigError(Exception):
    """Configuration absente ou invalide. Le message ne contient jamais de secret."""


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    user: str
    from_address: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    stock_db_id: str
    ventes_db_id: str
    catalogue_db_id: str
    commandes_db_id: str
    llm_model: str
    date_reference: date
    smtp: SmtpSettings | None
    trace_dir: Path
    notion_token: str = field(repr=False)
    google_api_key: str = field(repr=False)
    mistral_api_key: str | None = field(default=None, repr=False)
    fallback_model: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        def get(name: str) -> str:
            return (env.get(name) or "").strip()

        errors: list[str] = []
        missing = [name for name in REQUIRED if not get(name)]
        if missing:
            errors.append("variables manquantes : " + ", ".join(missing))

        raw_date = get("DATE_REFERENCE") or DEFAULT_DATE_REFERENCE
        try:
            date_reference = date.fromisoformat(raw_date)
        except ValueError:
            errors.append("DATE_REFERENCE doit être au format AAAA-MM-JJ")
            date_reference = date.fromisoformat(DEFAULT_DATE_REFERENCE)

        smtp = None
        smtp_present = [name for name in SMTP_VARS if get(name)]
        if smtp_present:
            smtp_missing = [name for name in SMTP_VARS if not get(name)]
            if smtp_missing:
                errors.append(
                    "configuration SMTP incomplète, il manque : " + ", ".join(smtp_missing)
                )
            elif not get("SMTP_PORT").isdigit():
                errors.append("SMTP_PORT doit être un nombre")
            else:
                smtp = SmtpSettings(
                    host=get("SMTP_HOST"),
                    port=int(get("SMTP_PORT")),
                    user=get("SMTP_USER"),
                    password=get("SMTP_PASSWORD"),
                    from_address=get("SMTP_FROM"),
                )

        if errors:
            raise ConfigError("Configuration invalide — " + " ; ".join(errors))

        mistral_key = get("MISTRAL_API_KEY") or None
        return cls(
            stock_db_id=get("STOCK_DB_ID"),
            ventes_db_id=get("VENTES_DB_ID"),
            catalogue_db_id=get("CATALOGUE_DB_ID"),
            commandes_db_id=get("COMMANDES_DB_ID"),
            llm_model=get("LLM_MODEL") or DEFAULT_MODEL,
            date_reference=date_reference,
            smtp=smtp,
            trace_dir=Path(get("TRACE_DIR") or "var"),
            notion_token=get("NOTION_TOKEN"),
            google_api_key=get("GOOGLE_API_KEY"),
            mistral_api_key=mistral_key,
            fallback_model=(get("FALLBACK_MODEL") or DEFAULT_FALLBACK_MODEL) if mistral_key else None,
        )


def load_settings() -> Settings:
    """Charge `.env` (sans écraser l'environnement existant) puis valide."""
    from dotenv import load_dotenv

    load_dotenv(override=False)
    return Settings.from_env(os.environ)
