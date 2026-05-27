import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import parse_cors_origins
from app.routers import parcels

app = FastAPI(
    title="Plinth Spatial Intelligence Platform API",
    version="0.2.0",
    description="Parcel boundary lookup via RapidAPI Property Lines.",
)

_DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
    "http://plinth-northeast-dwellings.lovable.app",
]
_cors_origins = parse_cors_origins(defaults=_DEFAULT_CORS_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(parcels.router, prefix="/parcels", tags=["Parcels"])


@app.on_event("startup")
async def startup_checks():
    print(f"CORS allow_origins: {_cors_origins}")
    if not os.environ.get("X-RAPIDAPI-KEY"):
        print(
            "WARNING: X-RAPIDAPI-KEY not set. "
            "Parcel search will return no_match until configured in backend/.env."
        )
    if not os.environ.get("RENTCAST_API_KEY"):
        print(
            "WARNING: RENTCAST_API_KEY not set. "
            "Parcel search will omit monthly rent until configured in backend/.env."
        )


@app.get("/")
def root():
    return {"service": "plinth-sip-api", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "plinth-sip-api"}
