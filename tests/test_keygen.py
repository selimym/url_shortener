import pytest
import string
from shortener_app.keygen import generate_random_key, generate_unique_random_key, key_exists
from shortener_app import models

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

@pytest.mark.asyncio
async def test_key_exists_false(test_db):
    """Test key_exists returns False for non-existent key."""
    async with test_db() as db:
        exists = await key_exists(db, "NOTEXIST")
        assert exists is False

@pytest.mark.asyncio
async def test_key_exists_true(test_db):
    """Test key_exists returns True for existing key."""
    async with test_db() as db:
        # Create a URL
        url = models.URL(
            target_url="https://example.com",
            key="TESTKEY",
            secret_key="SECRET123"
        )
        db.add(url)
        await db.commit()
        
        # Check it exists
        exists = await key_exists(db, "TESTKEY")
        assert exists is True

@pytest.mark.asyncio
async def test_generate_unique_random_key(test_db):
    """Test unique key generation."""
    async with test_db() as db:
        key = await generate_unique_random_key(db, size=6)
        assert len(key) == 6
        assert not await key_exists(db, key)

@pytest.mark.asyncio
async def test_generate_unique_random_key_avoids_collision(test_db):
    """Test that unique key generation avoids existing keys."""
    async with test_db() as db:
        # Create URL with a specific key
        existing_key = "EXIST1"
        url = models.URL(
            target_url="https://example.com",
            key=existing_key,
            secret_key="SECRET123"
        )
        db.add(url)
        await db.commit()
        
        # Generate new unique key - should be different
        new_key = await generate_unique_random_key(db, size=6)
        assert new_key != existing_key
