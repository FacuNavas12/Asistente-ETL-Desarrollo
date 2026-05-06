from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import ai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai.router)


@app.get("/")
async def read_rout():
    return {"message": "FastAPI funciona TEST TEST!"}

