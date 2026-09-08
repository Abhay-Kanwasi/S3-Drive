import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.router import api_router
from core.config import settings


@asynccontextmanager
async def app_init(app: FastAPI):
    app.include_router(api_router, prefix=settings.API_V1_STR)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=app_init,
)

# CORS: explicit origins required when allow_credentials=True.
# Populate BACKEND_CORS_ORIGINS in .env with the frontend origin(s).
_origins = [origin.strip().rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]
_origins = _origins or ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Endpoints exempt from CSRF — unauthenticated POST flows
_CSRF_EXEMPT_PATHS = {
    f"{settings.API_V1_STR}/auth/google",
    f"{settings.API_V1_STR}/auth/onboard",
}


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    if settings.ENV == "test":
        return await call_next(request)

    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return await call_next(request)

    if request.url.path in _CSRF_EXEMPT_PATHS:
        return await call_next(request)

    cookie_token = request.cookies.get("s3exp_csrf")
    header_token = request.headers.get(settings.CSRF_HEADER_NAME)

    if (
        not cookie_token
        or not header_token
        or not secrets.compare_digest(cookie_token, header_token)
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "CSRF validation failed"},
        )

    return await call_next(request)




@app.get(f"{settings.API_V1_STR}/health")
def healthCheck():
    return {"status": "healthy"}
