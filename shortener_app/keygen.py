import random
import string


def generate_random_key(size: int = 6) -> str:
    """Uniqueness enforced by database constraint, not pre-checking (avoids TOCTOU)."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=size))