"""Assemblage de l'agent : create_agent (LangGraph) + verrou de validation humaine.

`passer_commande` est la seule action irréversible : le graphe s'interrompt
avant son exécution (HumanInTheLoopMiddleware). Madeleine peut seulement
valider ou refuser, pas modifier les arguments. Le checkpointer conserve tout
l'état de la conversation (y compris les ToolMessages) par thread.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    InterruptOnConfig,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver

from boulangerie.config import Settings
from boulangerie.prompt import render_system_prompt

OUTILS_A_VALIDER = {
    "passer_commande": InterruptOnConfig(
        allowed_decisions=["approve", "reject"],
        description="Envoi de l'email de commande et enregistrement de la commande",
    )
}


def build_agent(
    model: BaseChatModel,
    tools: list,
    date_reference: date,
    *,
    fallback: BaseChatModel | None = None,
    checkpointer: Any | None = None,
    max_retries: int = 2,
    limite_appels_modele: int = 12,
):
    # Borne le nombre d'appels au modèle par message de Madeleine (boucle d'outils, coût).
    middleware: list = [ModelCallLimitMiddleware(run_limit=limite_appels_modele, exit_behavior="error")]
    if fallback is not None:
        middleware.append(ModelFallbackMiddleware(fallback))
    if max_retries > 0:
        middleware.append(ModelRetryMiddleware(max_retries=max_retries, initial_delay=2.0, on_failure="error"))
    middleware.append(HumanInTheLoopMiddleware(interrupt_on=OUTILS_A_VALIDER))
    return create_agent(
        model,
        tools,
        system_prompt=render_system_prompt(date_reference),
        middleware=middleware,
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
        name="alexandre",
    )


def build_chat_models(settings: Settings) -> tuple[BaseChatModel, BaseChatModel | None]:
    """Gemini en modèle principal ; Mistral en secours si sa clé est fournie."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    principal = ChatGoogleGenerativeAI(
        model=settings.llm_model, google_api_key=settings.google_api_key, temperature=0
    )
    secours = None
    if settings.mistral_api_key and settings.fallback_model:
        from langchain_mistralai import ChatMistralAI

        secours = ChatMistralAI(model=settings.fallback_model, api_key=settings.mistral_api_key, temperature=0)
    return principal, secours
