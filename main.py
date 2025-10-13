import models, schemas, crud
from database import engine
from config import get_settings

import validators
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.datastructures import URL

app = FastAPI()
models.Base.metadata.create_all(bind=engine)


def get_db():
    with Session(engine) as session:
        yield session


def raise_bad_request(message):
    raise HTTPException(status_code=400, detail=message)


def raise_not_found(request):
    message = f"URL '{request.url}' doesn't exist"
    raise HTTPException(status_code=404, detail=message)


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
def create_url(url: schemas.URLBase, db: Session = Depends(get_db)):
    if not validators.url(url.target_url):
        raise raise_bad_request("Your provided URL is not valid")
    db_url = crud.create_db_url(db, url)
    return get_admin_info(db_url)


@app.get("/{url_key}")
def forward_to_target_url(
        url_key: str,
        request: Request,
        db: Session = Depends(get_db)
    ):
    db_url = crud.get_db_url_by_key(db=db, url_key=url_key)
    if db_url:
        #Redirect is not cached locally because we want the request to hit the db for analytics
        return RedirectResponse(db_url.target_url)
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}",
    name="admin info",
    response_model=schemas.URLInfo,
)
def get_url_info(
    secret_key: str, request: Request, db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        return get_admin_info(db_url)
    else:
        raise_not_found(request)