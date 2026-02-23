import string
from shortener_app.keygen import generate_random_key


def test_generate_random_key_length():
    """Test random key has correct length."""
    key = generate_random_key(size=6)
    assert len(key) == 6

    key = generate_random_key(size=10)
    assert len(key) == 10


def test_generate_random_key_characters():
    """Test random key contains only valid characters."""
    valid_chars = set(string.ascii_uppercase + string.digits)

    for _ in range(100):  # Test multiple times for randomness
        key = generate_random_key(size=6)
        assert all(c in valid_chars for c in key)


def test_generate_random_key_uniqueness():
    """Test that generated keys are (usually) different."""
    keys = [generate_random_key(size=6) for _ in range(100)]
    # With 36^6 possibilities, 100 keys should be unique
    assert len(set(keys)) == 100

