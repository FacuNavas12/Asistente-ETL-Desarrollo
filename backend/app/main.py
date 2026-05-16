import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.log_filters import PasswordFilter
from app.routers import ai, connections

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger().addFilter(PasswordFilter())

app = FastAPI(title="Acelerador ETL — API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # frontend dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai.router)
app.include_router(connections.router)


@app.get("/")
async def health():
    return {"status": "ok"}
