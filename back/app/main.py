from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from api.api import api_router

app = FastAPI(
    title="Game Nyamnyam API"
)

# CORS 설정
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
