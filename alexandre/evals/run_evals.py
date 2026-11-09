"""Évaluations live : vrai modèle (Gemini), données de test, k essais par scénario.

Usage (depuis alexandre/) :
    .venv/bin/python -m evals.run_evals --k 3 [--scenario S4] [--pause 4]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from boulangerie.agent import build_chat_models
from boulangerie.config import load_settings
from evals.harness import Synthese, jouer, rapport
from evals.scenarios import SCENARIOS

DOSSIER_RAPPORTS = Path(__file__).parent / "reports"


async def evaluer(k: int, ids: list[str] | None = None, pause: float = 4.0) -> tuple[list[Synthese], str]:
    settings = load_settings()
    principal, secours = build_chat_models(settings)
    scenarios = [s for s in SCENARIOS if not ids or s.id in ids]
    syntheses = []
    for scenario in scenarios:
        resultats = []
        for essai in range(1, k + 1):
            resultat = await jouer(scenario, principal, essai=essai, fallback=secours)
            etat = "OK " if resultat.ok else "KO "
            print(f"{scenario.id} essai {essai}/{k} : {etat}{resultat.echecs() or ''}", flush=True)
            resultats.append(resultat)
            await asyncio.sleep(pause)  # niveau gratuit : on espace les appels
        syntheses.append(Synthese(scenario.id, resultats))
    return syntheses, rapport(syntheses, settings.llm_model, k)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=1, help="essais par scénario (défaut 1)")
    parser.add_argument("--scenario", action="append", help="limiter à un scénario (répétable)")
    parser.add_argument("--pause", type=float, default=4.0, help="secondes entre deux essais")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    syntheses, texte = asyncio.run(evaluer(args.k, args.scenario, args.pause))
    DOSSIER_RAPPORTS.mkdir(exist_ok=True)
    chemin = DOSSIER_RAPPORTS / f"rapport-{datetime.now():%Y%m%d-%H%M%S}.md"
    chemin.write_text(texte, encoding="utf-8")
    total = len(syntheses)
    print(
        f"\npass@1 {sum(s.pass_at_1 for s in syntheses)}/{total} — "
        f"pass@k {sum(s.pass_at_k for s in syntheses)}/{total} — "
        f"pass^k {sum(s.pass_hat_k for s in syntheses)}/{total}\nRapport : {chemin}"
    )


if __name__ == "__main__":
    main()
