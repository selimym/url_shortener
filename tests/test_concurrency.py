import pytest
import asyncio
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_concurrent_clicks_race_condition(client):
    """Test that concurrent clicks don't lose count due to race condition."""
    # Create a URL
    create_response = await client.post(
        "/url",
        json={"target_url": "https://www.example.com"}
    )
    data = create_response.json()
    url_key = data["url"].split("/")[-1]
    secret_key = data["admin_url"].split("/")[-1]
    
    # Simulate 10 concurrent clicks
    num_clicks = 10
    tasks = [
        client.get(f"/{url_key}", follow_redirects=False)
        for _ in range(num_clicks)
    ]
    
    # Execute all clicks simultaneously
    await asyncio.gather(*tasks)
    
    # Check final count
    admin_response = await client.get(f"/admin/{secret_key}")
    final_count = admin_response.json()["clicks"]
    
    # This will FAIL with current code due to race condition
    assert final_count == num_clicks, f"Expected {num_clicks} clicks, got {final_count}"


@pytest.mark.asyncio
async def test_high_concurrency_clicks(client):
    """Test with even higher concurrency to stress test the system."""
    create_response = await client.post(
        "/url",
        json={"target_url": "https://www.example.com"}
    )
    data = create_response.json()
    url_key = data["url"].split("/")[-1]
    secret_key = data["admin_url"].split("/")[-1]
    
    # Simulate 50 concurrent clicks
    num_clicks = 50
    tasks = [
        client.get(f"/{url_key}", follow_redirects=False)
        for _ in range(num_clicks)
    ]
    
    await asyncio.gather(*tasks)
    
    admin_response = await client.get(f"/admin/{secret_key}")
    final_count = admin_response.json()["clicks"]
    
    # With race condition, this might show 45-49 instead of 50
    assert final_count == num_clicks, f"Lost {num_clicks - final_count} clicks due to race condition"


@pytest.mark.asyncio
async def test_multiple_urls_concurrent_access(client):
    """Test concurrent access to different URLs doesn't interfere."""
    # Create multiple URLs
    urls = []
    for i in range(3):
        response = await client.post(
            "/url",
            json={"target_url": f"https://example{i}.com"}
        )
        data = response.json()
        urls.append({
            "key": data["url"].split("/")[-1],
            "secret": data["admin_url"].split("/")[-1]
        })
    
    # Concurrent clicks on different URLs
    tasks = []
    clicks_per_url = 5
    for url_data in urls:
        for _ in range(clicks_per_url):
            tasks.append(client.get(f"/{url_data['key']}", follow_redirects=False))
    
    # Shuffle to interleave requests
    import random
    random.shuffle(tasks)
    await asyncio.gather(*tasks)
    
    # Verify each URL has correct count
    for url_data in urls:
        admin_response = await client.get(f"/admin/{url_data['secret']}")
        count = admin_response.json()["clicks"]
        assert count == clicks_per_url, f"URL {url_data['key']} has {count} clicks, expected {clicks_per_url}"

@pytest.mark.asyncio
async def test_concurrent_url_creation_unique_keys(client):
    """Test that concurrent URL creation generates unique keys."""
    target_url = "https://www.example.com"
    num_concurrent = 20
    
    # Create many URLs concurrently
    tasks = [
        client.post("/url", json={"target_url": target_url})
        for _ in range(num_concurrent)
    ]
    
    responses = await asyncio.gather(*tasks)
    
    # Extract all keys
    keys = [resp.json()["url"].split("/")[-1] for resp in responses]
    
    # All keys should be unique
    assert len(keys) == len(set(keys)), f"Duplicate keys generated: {len(keys)} total, {len(set(keys))} unique"


@pytest.mark.asyncio
async def test_concurrent_key_generation_no_collision(test_db):
    """Test key generation under high concurrency doesn't create duplicates."""
    from shortener_app import keygen
    
    async with test_db() as db:
        # Generate many keys concurrently
        num_keys = 100
        tasks = [
            keygen.generate_unique_random_key(db, size=6)
            for _ in range(num_keys)
        ]
        
        keys = await asyncio.gather(*tasks)
        
        # All should be unique
        assert len(keys) == len(set(keys)), "Duplicate keys generated during concurrent creation"


@pytest.mark.asyncio
async def test_concurrent_delete_and_access(client):
    """Test what happens when URL is deleted while being accessed."""
    # Create URL
    create_response = await client.post(
        "/url",
        json={"target_url": "https://www.example.com"}
    )
    data = create_response.json()
    url_key = data["url"].split("/")[-1]
    secret_key = data["admin_url"].split("/")[-1]
    
    # Concurrent delete and access
    delete_task = client.delete(f"/admin/{secret_key}")
    access_tasks = [
        client.get(f"/{url_key}", follow_redirects=False)
        for _ in range(5)
    ]
    
    results = await asyncio.gather(delete_task, *access_tasks)
    
    # Delete should succeed
    assert results[0].status_code == 200
    
    # Some accesses might succeed (before delete), some fail (after delete)
    # But none should crash or cause database corruption
    for result in results[1:]:
        assert result.status_code in [307, 404], "Unexpected status during concurrent delete"


@pytest.mark.asyncio
async def test_concurrent_admin_access(client):
    """Test concurrent admin info requests don't cause issues."""
    # Create URL
    create_response = await client.post(
        "/url",
        json={"target_url": "https://www.example.com"}
    )
    secret_key = create_response.json()["admin_url"].split("/")[-1]
    
    # Multiple concurrent admin requests
    tasks = [
        client.get(f"/admin/{secret_key}")
        for _ in range(20)
    ]
    
    responses = await asyncio.gather(*tasks)
    
    # All should succeed with same data
    for response in responses:
        assert response.status_code == 200
        data = response.json()
        assert data["target_url"] == "https://www.example.com"


@pytest.mark.asyncio
async def test_many_sequential_requests_no_memory_leak(client):
    """Test that many sequential requests don't leak resources."""
    # Create URL once
    create_response = await client.post(
        "/url",
        json={"target_url": "https://www.example.com"}
    )
    url_key = create_response.json()["url"].split("/")[-1]
    
    # Make many sequential requests
    for i in range(100):
        response = await client.get(f"/{url_key}", follow_redirects=False)
        assert response.status_code == 307
    
    # If database connections aren't closed, this will fail


@pytest.mark.asyncio
async def test_database_connection_cleanup(test_db):
    """Test that database sessions are properly closed."""
    from shortener_app import crud, schemas
    
    # Create many sessions and operations
    for i in range(50):
        async with test_db() as db:
            url_data = schemas.URLBase(target_url=f"https://example{i}.com")
            await crud.create_db_url(db, url_data)
    
    # If connections leak, this will exhaust the pool
    async with test_db() as db:
        result = await crud.get_db_url_by_id(db, 1)
        assert result is not None