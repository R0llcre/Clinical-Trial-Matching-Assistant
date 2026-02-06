from fastapi import FastAPI

from app.routes.health import router as health_router
from app.routes.patients import router as patients_router
from app.routes.trials import router as trials_router

app = FastAPI()
app.include_router(health_router)
app.include_router(patients_router)
app.include_router(trials_router)
