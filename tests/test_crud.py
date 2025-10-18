import pytest
from shortener_app import crud, schemas
 

@pytest.mark.asyncio
async def test_create_db_url(test_db):
    """Test creating URL in database."""
    async with test_db() as db:
        url_data = schemas.URLBase(target_url="https://example.com")
        db_url = await crud.create_db_url(db, url_data)
        
        assert db_url.target_url == "https://example.com"
        assert db_url.is_active is True
        assert db_url.clicks == 0
        assert len(db_url.key) == 6
        assert "_" in db_url.secret_key


@pytest.mark.asyncio
async def test_get_db_url_by_key(test_db):
    """Test retrieving URL by key."""
    async with test_db() as db:
        # Create URL
        url_data = schemas.URLBase(target_url="https://example.com")
        created_url = await crud.create_db_url(db, url_data)
        
        # Retrieve it
        retrieved_url = await crud.get_db_url_by_key(db, created_url.key)
        assert retrieved_url is not None
        assert retrieved_url.key == created_url.key
        assert retrieved_url.target_url == "https://example.com"


@pytest.mark.asyncio
async def test_get_db_url_by_key_not_found(test_db):
    """Test retrieving non-existent URL returns None."""
    async with test_db() as db:
        result = await crud.get_db_url_by_key(db, "NOTEXIST")
        assert result is None


@pytest.mark.asyncio
async def test_get_db_url_by_id(test_db):
    """Test retrieving URL by ID."""
    async with test_db() as db:
        # Create URL
        url_data = schemas.URLBase(target_url="https://example.com")
        created_url = await crud.create_db_url(db, url_data)
        
        # Retrieve by ID
        retrieved_url = await crud.get_db_url_by_id(db, created_url.id)
        assert retrieved_url is not None
        assert retrieved_url.id == created_url.id


@pytest.mark.asyncio
async def test_get_db_url_by_secret_key(test_db):
    """Test retrieving URL by secret key."""
    async with test_db() as db:
        # Create URL
        url_data = schemas.URLBase(target_url="https://example.com")
        created_url = await crud.create_db_url(db, url_data)
        
        # Retrieve by secret key
        retrieved_url = await crud.get_db_url_by_secret_key(db, created_url.secret_key)
        assert retrieved_url is not None
        assert retrieved_url.secret_key == created_url.secret_key


@pytest.mark.asyncio
async def test_update_db_clicks(test_db):
    """Test incrementing click counter."""
    async with test_db() as db:
        # Create URL
        url_data = schemas.URLBase(target_url="https://example.com")
        db_url = await crud.create_db_url(db, url_data)
        
        assert db_url.clicks == 0
        
        # Update clicks
        await crud.update_db_clicks(db, db_url)
        assert db_url.clicks == 1
        
        await crud.update_db_clicks(db, db_url)
        assert db_url.clicks == 2


@pytest.mark.asyncio
async def test_deactivate_db_url(test_db):
    """Test deactivating a URL."""
    async with test_db() as db:
        # Create URL
        url_data = schemas.URLBase(target_url="https://example.com")
        created_url = await crud.create_db_url(db, url_data)
        
        assert created_url.is_active is True
        
        # Deactivate it
        deactivated_url = await crud.deactivate_db_url(db, created_url.secret_key)
        assert deactivated_url is not None
        assert deactivated_url.is_active is False
        
        # Verify it's not returned by normal queries
        result = await crud.get_db_url_by_key(db, created_url.key)
        assert result is None  # Inactive URLs aren't returned


@pytest.mark.asyncio
async def test_deactivate_nonexistent_url(test_db):
    """Test deactivating non-existent URL returns None."""
    async with test_db() as db:
        result = await crud.deactivate_db_url(db, "NOTEXIST")
        assert result is None
