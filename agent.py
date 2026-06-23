from langchain.agents import create_agent
from tools.notion import lire_ventes,lire_stock,lire_catalogue,enregistrer_commande
from tools.email import envoyer_email
from tools.prevision import prevision_production
from langchain_mistralai import ChatMistralAI
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
with open("prompts/system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

tools=[
    lire_ventes,
    lire_stock,
    lire_catalogue,
    enregistrer_commande,
    envoyer_email,
    prevision_production
]
llm=ChatMistralAI(
    model="mistral-small-latest",
    temperature=0
)
agent=create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
)

def run_agent(messages:list)->str:
    try:
        response=agent.invoke({
            "messages":messages
                
            })
        return response["messages"][-1].content
    except Exception as e:
        return f"Erreur lors de l'exécution de l'agent : {e}"