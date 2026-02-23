import pytest
from shortener_app.services import URLService


@pytest.mark.asyncio
async def test_create_url(test_db):
    async with test_db() as db:
        service = URLService(db)
        url = await service.create("https://example.com")

        assert url.target_url == "https://example.com"
        assert url.is_active is True
        assert url.clicks == 0
        assert len(url.key) == 6
        assert "_" in url.secret_key


@pytest.mark.asyncio
async def test_get_by_key(test_db):
    async with test_db() as db:
        service = URLService(db)
        created = await service.create("https://example.com")

        retrieved = await service.get_by_key(created.key)
        assert retrieved is not None
        assert retrieved.key == created.key
        assert retrieved.target_url == "https://example.com"


@pytest.mark.asyncio
async def test_get_by_key_not_found(test_db):
    async with test_db() as db:
        service = URLService(db)
        result = await service.get_by_key("NOTEXIST")
        assert result is None


@pytest.mark.asyncio
async def test_get_by_secret_key(test_db):
    async with test_db() as db:
        service = URLService(db)
        created = await service.create("https://example.com")

        retrieved = await service.get_by_secret_key(created.secret_key)
        assert retrieved is not None
        assert retrieved.secret_key == created.secret_key


@pytest.mark.asyncio
async def test_increment_clicks(test_db):
    async with test_db() as db:
        service = URLService(db)
        url = await service.create("https://example.com")
        assert url.clicks == 0

        updated = await service.increment_clicks(url.id)
        assert updated.clicks == 1

        updated = await service.increment_clicks(url.id)
        assert updated.clicks == 2


@pytest.mark.asyncio
async def test_deactivate(test_db):
    async with test_db() as db:
        service = URLService(db)
        created = await service.create("https://example.com")
        assert created.is_active is True

        deactivated = await service.deactivate(created.secret_key)
        assert deactivated is not None
        assert deactivated.is_active is False

        result = await service.get_by_key(created.key)
        assert result is None


@pytest.mark.asyncio
async def test_deactivate_nonexistent(test_db):
    async with test_db() as db:
        service = URLService(db)
        result = await service.deactivate("NOTEXIST")
        assert result is None
