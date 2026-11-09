"""Live (exclu par défaut) : `pytest -m live evals`, avec EVAL_K essais par scénario (défaut 1)."""

import os

import pytest

from evals.run_evals import evaluer

pytestmark = pytest.mark.live


async def test_les_six_scenarios_atteignent_les_seuils():
    k = int(os.environ.get("EVAL_K", "1"))
    syntheses, texte = await evaluer(k)

    echecs = [s.scenario for s in syntheses if not s.pass_at_k]
    hallucinations = [s.scenario for s in syntheses if not s.critere_stable("aucun_chiffre_invente")]
    envoi_sans_validation = [s.scenario for s in syntheses if not s.critere_stable("arret_avant_envoi")]
    assert not echecs, f"scénarios en échec : {echecs}\n\n{texte}"
    assert not hallucinations, f"chiffres inventés : {hallucinations}\n\n{texte}"
    assert not envoi_sans_validation, f"envoi sans validation : {envoi_sans_validation}\n\n{texte}"
