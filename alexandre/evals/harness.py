"""Joue un scénario de bout en bout et applique les correcteurs."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from boulangerie.agent import build_agent
from boulangerie.conversation import Conversation
from boulangerie.notion_repo import NotionIds, NotionRepository
from boulangerie.prompt import render_system_prompt
from boulangerie.tools import Deps, build_tools
from evals.graders import chiffres_inventes, contient_jargon, lignes_non_vides
from evals.scenarios import Scenario
from tests.fakes import DB_CATALOGUE, DB_COMMANDES, DB_STOCK, DB_VENTES, FakeMailer, FakeNotionClient

DATE_REFERENCE = date(2026, 2, 16)
DESTINATAIRE_S4 = "commandes@minoterie-dupont.fr"
LIGNES_MAX = 10


@dataclass
class Resultat:
    scenario: str
    essai: int
    criteres: dict[str, tuple[bool, str]] = field(default_factory=dict)
    reponse: str = ""
    appels: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(passe for passe, _ in self.criteres.values())

    def echecs(self) -> dict[str, str]:
        return {nom: detail for nom, (passe, detail) in self.criteres.items() if not passe}


def _critere(erreur: str | None) -> tuple[bool, str]:
    return (erreur is None, erreur or "")


async def jouer(scenario: Scenario, model, *, essai: int = 1, fallback=None, max_retries: int = 2) -> Resultat:
    notion, mailer = FakeNotionClient(), FakeMailer()
    deps = Deps(
        repo=NotionRepository(notion, NotionIds(DB_STOCK, DB_VENTES, DB_CATALOGUE, DB_COMMANDES)),
        mailer=mailer,
        date_reference=DATE_REFERENCE,
        trace_dir=Path(tempfile.mkdtemp(prefix="eval-")),
        clock=lambda: datetime(2026, 11, 9, 10, 0),
    )
    agent = build_agent(model, build_tools(deps), DATE_REFERENCE, fallback=fallback, max_retries=max_retries)
    thread = f"eval-{scenario.id}-{essai}"
    conversation = Conversation(agent, thread_id=thread, repo=deps.repo)
    resultat = Resultat(scenario=scenario.id, essai=essai)
    messages_madeleine = [scenario.question]

    reponse = await conversation.envoyer(scenario.question)
    if scenario.commande:
        if reponse.validation is None and scenario.relance:
            messages_madeleine.append(scenario.relance)
            reponse = await conversation.envoyer(scenario.relance)
        arret = reponse.validation is not None and not mailer.sent and not notion.created
        resultat.criteres["arret_avant_envoi"] = _critere(
            None if arret else "le graphe ne s'est pas arrêté avant l'envoi (ou a envoyé sans validation)"
        )
        if reponse.validation is not None:
            reponse = await conversation.valider(approuve=True)
        envoi = (
            len(mailer.sent) == 1 and mailer.sent[0]["destinataire"] == DESTINATAIRE_S4 and len(notion.created) == 1
        )
        resultat.criteres["envoi_apres_validation"] = _critere(
            None if envoi else f"{len(mailer.sent)} email(s), {len(notion.created)} commande(s) enregistrée(s)"
        )

    etat = await agent.aget_state({"configurable": {"thread_id": thread}})
    messages = etat.values.get("messages", [])
    resultat.appels = [appel for m in messages if isinstance(m, AIMessage) for appel in m.tool_calls]
    resultat.reponse = reponse.texte or ""
    sources_outils = [m.content for m in messages if isinstance(m, ToolMessage)]
    contexte = messages_madeleine + [render_system_prompt(DATE_REFERENCE)]

    inventes = chiffres_inventes(resultat.reponse, sources_outils, contexte)
    jargon = contient_jargon(resultat.reponse)
    lignes = lignes_non_vides(resultat.reponse)
    resultat.criteres.update(
        {
            "outil": _critere(scenario.verifier_outils(resultat.appels)),
            "reponse": _critere(scenario.verifier_reponse(resultat.reponse)),
            "aucun_chiffre_invente": _critere(f"chiffres sans source : {inventes}" if inventes else None),
            "pas_de_jargon": _critere(f"jargon : {jargon}" if jargon else None),
            "concision": _critere(f"{lignes} lignes" if lignes > LIGNES_MAX else None),
        }
    )
    return resultat


@dataclass
class Synthese:
    scenario: str
    resultats: list[Resultat]

    @property
    def pass_at_1(self) -> bool:
        return self.resultats[0].ok

    @property
    def pass_at_k(self) -> bool:
        return any(r.ok for r in self.resultats)

    @property
    def pass_hat_k(self) -> bool:
        return all(r.ok for r in self.resultats)

    def critere_stable(self, nom: str) -> bool:
        return all(r.criteres.get(nom, (True, ""))[0] for r in self.resultats)


def rapport(syntheses: list[Synthese], modele: str, k: int) -> str:
    lignes = [
        f"# Rapport d'évaluation — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Modèle : `{modele}` — k = {k}",
        "",
        "| Scénario | pass@1 | pass@k | pass^k | Échecs |",
        "|---|---|---|---|---|",
    ]
    for s in syntheses:
        echecs = "; ".join(
            f"essai {r.essai} — " + ", ".join(f"{n} ({d})" for n, d in r.echecs().items())
            for r in s.resultats
            if not r.ok
        )
        marque = lambda b: "✅" if b else "❌"  # noqa: E731
        lignes.append(
            f"| {s.scenario} | {marque(s.pass_at_1)} | {marque(s.pass_at_k)} | {marque(s.pass_hat_k)} | {echecs or '—'} |"
        )
    total = len(syntheses)
    lignes += [
        "",
        f"pass@1 : {sum(s.pass_at_1 for s in syntheses)}/{total} — "
        f"pass@k : {sum(s.pass_at_k for s in syntheses)}/{total} — "
        f"pass^k : {sum(s.pass_hat_k for s in syntheses)}/{total}",
        "",
        "## Réponses",
        "",
    ]
    for s in syntheses:
        for r in s.resultats:
            appels = ", ".join(f"{a['name']}({a['args']})" for a in r.appels) or "aucun"
            lignes += [f"### {r.scenario} — essai {r.essai}", "", f"Appels : `{appels}`", "", "> " + r.reponse.replace("\n", "\n> "), ""]
    return "\n".join(lignes)
