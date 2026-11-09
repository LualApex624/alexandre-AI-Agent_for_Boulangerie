"""Hors ligne : les correcteurs détectent ce qu'ils doivent détecter."""

from evals.graders import chiffres, chiffres_inventes, contient_jargon


def test_extrait_les_nombres_en_notation_francaise_sans_les_numeros_de_liste():
    texte = "1. Beurre : **6 kg** à 7,50 €\n2. Marge de 65,6 %"

    assert chiffres(texte) == [6.0, 7.5, 65.6]


def test_un_chiffre_present_dans_les_resultats_d_outils_n_est_pas_invente():
    sources = ['{"quantite": 8, "seuil_alerte": 10, "prix_unitaire": 6.6}']

    assert chiffres_inventes("Il te reste **8 kg**, sous ton seuil de 10 kg (6,60 € le kg).", sources) == []


def test_un_chiffre_absent_des_sources_est_invente():
    sources = ['{"quantite": 8, "seuil_alerte": 10}']

    assert chiffres_inventes("Il te reste 12 kg de beurre.", sources) == [12.0]


def test_un_arrondi_une_somme_ou_une_difference_de_valeurs_lues_est_accepte():
    sources = ['{"quantite": 8, "seuil_alerte": 10, "marge_pct": 65.6, "a": 120, "b": 110}']

    assert chiffres_inventes("Il manque 2 kg, marge d'environ 66 %, soit 230 sur deux jours.", sources) == []


def test_une_date_du_calendrier_du_prompt_est_acceptee():
    contexte = ["Demain, c'est le mardi 17/02/2026 (2026-02-17)."]

    assert chiffres_inventes("Pour demain mardi 17 février 2026 :", [], contexte) == []


def test_les_nombres_du_contexte_ne_servent_pas_a_fabriquer_des_chiffres():
    # 25 = 15 + 10 avec deux nombres du prompt : ce n'est pas une valeur lue dans un outil.
    contexte = ["Calendrier : 15/02, marge de 10 %."]

    assert chiffres_inventes("Commande 25 kg.", ['{"quantite": 8}'], contexte) == [25.0]


def test_detecte_le_jargon_technique():
    assert contient_jargon("Je vais interroger ta base de données Notion.") == ["base de données", "notion"]
    assert contient_jargon("Il te reste 8 kg de beurre.") == []
