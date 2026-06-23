import chainlit as cl
from agent import run_agent


@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="📦 Vérifier un stock",
            message="Quel est mon stock de beurre ?",
        ),
        cl.Starter(
            label="📊 Consulter les ventes",
            message="Combien de croissants j'ai vendu la semaine du 10 au 16 février ?",
        ),
        cl.Starter(
            label="🥖 Prévision production",
            message="Qu'est-ce que je dois préparer pour samedi ?",
        ),
        cl.Starter(
            label="📋 Infos produit",
            message="Donne-moi les infos sur la baguette tradition",
        ),
    ]


@cl.on_chat_start
async def start():
    cl.user_session.set("history", [])


@cl.on_message
async def main(message: cl.Message):
    history = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})
    response = run_agent(history)
    history.append({"role": "assistant", "content": response})
    cl.user_session.set("history", history)
    await cl.Message(content=response).send()
