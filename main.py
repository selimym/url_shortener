import random
import string

import validators
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import models, schemas
from database import engine


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


def generate_random_key(size: int):
    """
    Generate a random key of a given size.
    There are 62 possible characters so 62^size possible keys.
    """
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=size))


def add_url_to_db(db: Session, url: schemas.URLBase, key: str, secret_key: str) -> models.URL:
    db_url = models.URL(
        target_url=url.target_url, key=key, secret_key=secret_key
    )
    db.add(db_url)
    db.commit()
    db.refresh(db_url)
    return db_url

@app.post("/url", response_model=schemas.URLInfo)
def create_url(url: schemas.URLBase, db: Session = Depends(get_db)):
    if not validators.url(url.target_url):
        raise raise_bad_request("Your provided URL is not valid")

    key = generate_random_key(6)
    secret_key = generate_random_key(6)
    
    db_url = add_url_to_db(db, url, key, secret_key)
    
    return schemas.URLInfo(
        target_url=db_url.target_url,
        is_active=db_url.is_active,
        clicks=db_url.clicks,
        url=key,
        admin_url=secret_key
    )


@app.get("/{url_key}")
def forward_to_target_url(url_key: str, request: Request, db: Session = Depends(get_db)):
    db_url = (
        db.query(models.URL)
        .filter(models.URL.key == url_key, models.URL.is_active)
        .first()
    )
    if db_url:
        return RedirectResponse(db_url.target_url)
    else:
        raise_not_found(request)