"""Point d'entrée C : chargement de la configuration et rendu du prompt système."""

from datetime import date

import pytest

from boulangerie.config import ConfigError, Settings
from boulangerie.prompt import render_system_prompt

ENV_COMPLET = {
    "NOTION_TOKEN": "secret-notion",
    "STOCK_DB_ID": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    "VENTES_DB_ID": "b1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    "CATALOGUE_DB_ID": "c1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    "COMMANDES_DB_ID": "d1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    "GOOGLE_API_KEY": "secret-google",
    "SMTP_HOST": "sandbox.smtp.mailtrap.io",
    "SMTP_PORT": "587",
    "SMTP_USER": "user",
    "SMTP_PASSWORD": "secret-smtp",
    "SMTP_FROM": "madeleine@chez-madeleine.fr",
}


def test_charge_une_configuration_complete_avec_les_valeurs_par_defaut():
    settings = Settings.from_env(ENV_COMPLET)

    assert settings.stock_db_id == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
    assert settings.smtp is not None and settings.smtp.port == 587
    assert settings.llm_model == "gemini-3.5-flash"
    assert settings.date_reference == date(2026, 2, 16)
    assert settings.fallback_model is None


def test_liste_toutes_les_variables_manquantes_sans_reveler_les_secrets():
    env = {k: v for k, v in ENV_COMPLET.items() if k not in {"NOTION_TOKEN", "VENTES_DB_ID"}}

    with pytest.raises(ConfigError) as exc:
        Settings.from_env(env)

    message = str(exc.value)
    assert "NOTION_TOKEN" in message
    assert "VENTES_DB_ID" in message
    assert "secret-google" not in message


def test_sans_aucune_variable_smtp_l_envoi_d_email_est_desactive():
    env = {k: v for k, v in ENV_COMPLET.items() if not k.startswith("SMTP_")}

    assert Settings.from_env(env).smtp is None


def test_une_configuration_smtp_incomplete_est_refusee():
    env = {k: v for k, v in ENV_COMPLET.items() if k != "SMTP_PASSWORD"}

    with pytest.raises(ConfigError, match="SMTP_PASSWORD"):
        Settings.from_env(env)


def test_refuse_une_date_de_reference_invalide():
    with pytest.raises(ConfigError, match="DATE_REFERENCE"):
        Settings.from_env({**ENV_COMPLET, "DATE_REFERENCE": "16/02/2026"})


def test_refuse_un_port_smtp_non_numerique():
    with pytest.raises(ConfigError, match="SMTP_PORT"):
        Settings.from_env({**ENV_COMPLET, "SMTP_PORT": "abc"})


def test_le_fallback_mistral_est_actif_seulement_si_sa_cle_est_fournie():
    settings = Settings.from_env({**ENV_COMPLET, "MISTRAL_API_KEY": "secret-mistral"})

    assert settings.fallback_model == "mistral-small-latest"


def test_les_secrets_n_apparaissent_pas_dans_la_representation():
    texte = repr(Settings.from_env(ENV_COMPLET))

    for secret in ("secret-notion", "secret-google", "secret-smtp"):
        assert secret not in texte


def test_le_prompt_contient_le_calendrier_calcule_depuis_la_date_de_reference():
    prompt = render_system_prompt(date(2026, 2, 16))

    assert "lundi 16/02/2026" in prompt  # aujourd'hui
    assert "dimanche 15/02/2026" in prompt  # hier
    assert "mardi 17/02/2026" in prompt  # demain
    assert "du lundi 09/02/2026 au dimanche 15/02/2026" in prompt  # semaine dernière
    assert "{" not in prompt  # aucun gabarit non rendu


def test_le_prompt_suit_la_date_de_reference_configuree():
    prompt = render_system_prompt(date(2026, 2, 20))

    assert "vendredi 20/02/2026" in prompt
    assert "samedi 21/02/2026" in prompt


def test_le_prompt_respecte_la_taille_demandee_par_le_cahier_des_charges():
    lignes = [l for l in render_system_prompt(date(2026, 2, 16)).splitlines() if l.strip()]

    assert 80 <= len(lignes) <= 120


def test_le_port_du_serveur_vaut_8000_par_defaut_et_se_configure():
    assert Settings.from_env(ENV_COMPLET).port == 8000
    assert Settings.from_env({**ENV_COMPLET, "PORT": "8123"}).port == 8123


def test_un_port_invalide_est_refuse():
    with pytest.raises(ConfigError, match="PORT"):
        Settings.from_env({**ENV_COMPLET, "PORT": "huit-mille"})


def test_par_defaut_le_serveur_n_ecoute_qu_en_local():
    settings = Settings.from_env(ENV_COMPLET)

    assert settings.host == "127.0.0.1"
    assert settings.access_password is None
    assert settings.origines_autorisees == ()


def test_une_exposition_publique_sans_mot_de_passe_est_refusee():
    with pytest.raises(ConfigError, match="ACCESS_PASSWORD"):
        Settings.from_env({**ENV_COMPLET, "HOST": "0.0.0.0"})


def test_exposition_publique_avec_mot_de_passe_et_origines():
    settings = Settings.from_env({
        **ENV_COMPLET,
        "HOST": "0.0.0.0",
        "ACCESS_PASSWORD": "sesame",
        "ALLOWED_ORIGINS": "https://alexandre.example.com, https://autre.example.com/",
        "RENDER_EXTERNAL_URL": "https://alexandre.onrender.com",
    })

    assert settings.host == "0.0.0.0"
    assert settings.access_password == "sesame"
    assert settings.origines_autorisees == (
        "https://alexandre.example.com",
        "https://autre.example.com",
        "https://alexandre.onrender.com",
    )


def test_le_mot_de_passe_d_acces_n_apparait_pas_dans_la_representation():
    settings = Settings.from_env({**ENV_COMPLET, "ACCESS_PASSWORD": "sesame"})

    assert "sesame" not in repr(settings)


def test_le_client_gemini_echoue_vite_quand_le_quota_est_epuise():
    from boulangerie.agent import build_chat_models

    principal, _ = build_chat_models(Settings.from_env(ENV_COMPLET))

    # Défaut de la bibliothèque : 6 relances (plus d'une minute avant l'erreur).
    assert principal.max_retries == 1
    assert principal.timeout == 30
