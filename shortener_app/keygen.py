import random
import string


def generate_random_key(size: int = 6) -> str:
    """Generate a random key of uppercase letters and digits.

    Note: Uniqueness is enforced by database constraint + retry logic in crud.py,
    not by checking before insertion (which would create TOCTOU race conditions).
    """
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=size))