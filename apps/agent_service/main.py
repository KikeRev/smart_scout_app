from fastapi import FastAPI
from apps.agent_service.routers import players, news, chat
import langchain

langchain.debug = True       
langchain.verbose = True

app = FastAPI(title="Smart-Scout API")
app.include_router(players.router)
app.include_router(news.router)
app.include_router(chat.router)