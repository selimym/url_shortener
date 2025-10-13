import keygen, models, schemas

from sqlalchemy import select
from sqlalchemy.orm import Session


def create_db_url(db: Session, url: schemas.URLBase) -> models.URL:
    key = keygen.generate_unique_random_key(db, size=6)
    secret_key = f"{key}_{keygen.generate_random_key(size=8)}"
    db_url = models.URL(
        target_url=url.target_url, key=key, secret_key=secret_key
    )
    db.add(db_url)
    db.commit()
    db.refresh(db_url)
    return db_url


def get_db_url_by_key(db: Session, url_key: str) -> models.URL | None:
    stmt = select(models.URL).where(
        models.URL.key == url_key,
        models.URL.is_active == True
    )
    return db.scalars(stmt).first()


def get_db_url_by_id(db: Session, url_id: int) -> models.URL | None:
    return db.get(models.URL, url_id)
