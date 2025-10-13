import crud

import random
import string

from sqlalchemy.orm import Session


def generate_random_key(size: int = 6):
    """
    Generate a random key of a given size.
    There are 62 possible characters so 62^size possible keys.
    """
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=size))

def generate_unique_random_key(db: Session, size: int = 6) -> str:
    """
    Generate a random key that is unique in the database.
    """
    key = generate_random_key()
    #The higher the size of the key, the less likely it is to collide
    while crud.get_db_url_by_key(db, key):
        key = generate_random_key(size)
    return key