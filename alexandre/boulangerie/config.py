"""Configuration typée, lue une seule fois au démarrage depuis l'environnement.

Les secrets ne vivent que dans les variables d'environnement (fichier `.env`
local, jamais commité). Ils sont exclus de la représentation des objets pour
ne jamais finir dans un log ou un message d'erreur.
"""

from __future__ import annotations

import os
import re
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
LOOPBACK = ("127.0.0.1", "localhost", "::1")
SMTP_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM")

NOTION_ID = re.compile(r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$")
NOTION_DB_VARS = ("STOCK_DB_ID", "VENTES_DB_ID", "CATALOGUE_DB_ID", "COMMANDES_DB_ID")

DEFAULT_MODEL = "gemini-3.5-flash"
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
    port: int = 8000
    host: str = "127.0.0.1"
    access_password: str | None = field(default=None, repr=False)
    origines_autorisees: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        def get(name: str) -> str:
            return (env.get(name) or "").strip()

        errors: list[str] = []
        missing = [name for name in REQUIRED if not get(name)]
        if missing:
            errors.append("variables manquantes : " + ", ".join(missing))

        mal_formes = [name for name in NOTION_DB_VARS if get(name) and not NOTION_ID.fullmatch(get(name))]
        if mal_formes:
            errors.append("identifiants Notion mal formés (32 caractères hexadécimaux attendus) : " + ", ".join(mal_formes))

        raw_date = get("DATE_REFERENCE") or DEFAULT_DATE_REFERENCE
        try:
            date_reference = date.fromisoformat(raw_date)
        except ValueError:
            errors.append("DATE_REFERENCE doit être au format AAAA-MM-JJ")
            date_reference = date.fromisoformat(DEFAULT_DATE_REFERENCE)

        port = get("PORT") or "8000"
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            errors.append("PORT doit être un numéro de port (1 à 65535)")
            port = "8000"

        host = get("HOST") or "127.0.0.1"
        access_password = get("ACCESS_PASSWORD") or None
        if host not in LOOPBACK and not access_password:
            errors.append("ACCESS_PASSWORD est obligatoire quand HOST n'est pas local (127.0.0.1)")
        origines = tuple(
            o.strip().rstrip("/")
            for o in (get("ALLOWED_ORIGINS").split(",") + [get("RENDER_EXTERNAL_URL")])
            if o.strip()
        )

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
            port=int(port),
            host=host,
            access_password=access_password,
            origines_autorisees=origines,
        )


def load_settings() -> Settings:
    """Charge `.env` (sans écraser l'environnement existant) puis valide."""
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True), override=False)
    return Settings.from_env(os.environ)
