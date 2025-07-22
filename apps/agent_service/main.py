from fastapi import FastAPI
from apps.agent_service.routers import players

app = FastAPI(title="Smart-Scout API")
app.include_router(players.router)
