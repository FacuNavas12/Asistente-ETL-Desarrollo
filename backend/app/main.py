from fastapi import FastAPI
from app.routers import ai

app = FastAPI()

app.include_router(ai.router)


@app.get("/")
async def read_rout():
    return {"message": "FastAPI funciona TEST TEST!"}

