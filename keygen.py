import random
import string

def generate_random_key(size: int):
    """
    Generate a random key of a given size.
    There are 62 possible characters so 62^size possible keys.
    """
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=size))