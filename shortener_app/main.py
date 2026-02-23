from . import models, schemas
from .database import engine, AsyncSessionLocal
from .config import get_settings
from .services import URLService

import validators
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import URL

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Auto-create tables only in test mode (when not using migrations)
    if not get_settings().use_migrations:
        async with engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)

    yield

    await engine.dispose()

app = FastAPI(lifespan=lifespan)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def get_url_service(db: AsyncSession = Depends(get_db)) -> URLService:
    return URLService(db)

def raise_bad_request(message):
    raise HTTPException(status_code=400, detail=message)

def raise_not_found(request):
    message = f"URL '{request.url}' doesn't exist"
    raise HTTPException(status_code=404, detail=message)


@app.get("/")
def read_root():
    """Root endpoint - welcome message."""
    return {"message": "Welcome to the URL shortener API"}


def get_admin_info(db_url: models.URL) -> schemas.URLInfo:
    base_url = URL(get_settings().base_url)
    admin_endpoint = app.url_path_for(
        "admin info", secret_key=db_url.secret_key
    )
    return schemas.URLInfo(
        target_url=db_url.target_url,
        is_active=db_url.is_active,
        clicks=db_url.clicks,
        url=str(base_url.replace(path=db_url.key)),
        admin_url=str(base_url.replace(path=admin_endpoint))
    )


@app.post("/url", response_model=schemas.URLInfo)
async def create_url(url: schemas.URLBase, service: URLService = Depends(get_url_service)):
    if not validators.url(url.target_url):
        raise_bad_request("Your provided URL is not valid")
    db_url = await service.create(target_url=url.target_url)
    return get_admin_info(db_url)


@app.get("/{url_key}")
async def forward_to_target_url(
        url_key: str,
        request: Request,
        service: URLService = Depends(get_url_service)
    ):
    db_url = await service.get_by_key_with_lock(url_key)
    if db_url:
        await service.increment_clicks(db_url.id)
        return RedirectResponse(db_url.target_url)
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}",
    name="admin info",
    response_model=schemas.URLInfo,
)
async def get_url_info(
    secret_key: str, request: Request, service: URLService = Depends(get_url_service)
):
    if db_url := await service.get_by_secret_key(secret_key):
        return get_admin_info(db_url)
    else:
        raise_not_found(request)


@app.delete("/admin/{secret_key}")
async def delete_url(
    secret_key: str, request: Request, service: URLService = Depends(get_url_service)
):
    if db_url := await service.deactivate(secret_key):
        message = f"Successfully deleted shortened URL for '{db_url.target_url}'"
        return {"detail": message}
    else:
        raise_not_found(request)
