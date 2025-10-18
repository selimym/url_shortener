import pytest

@pytest.mark.asyncio
async def test_create_url_success(client):
    """Test successful URL creation."""
    response = await client.post(
        "/url",
        json={"target_url": "https://example.com"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_url"] == "https://example.com"
    assert data["is_active"] is True
    assert data["clicks"] == 0
    # Fix: url contains the full URL, not just the key
    assert data["url"].startswith("http://")
    assert len(data["url"].split("/")[-1]) == 6  # Key part is 6 chars
    assert "_" in data["admin_url"]


@pytest.mark.asyncio
async def test_create_url_invalid(client):
    """Test URL creation with invalid URL."""
    response = await client.post(
        "/url",
        json={"target_url": "not-a-valid-url"}
    )
    assert response.status_code == 400
    assert "not valid" in response.json()["detail"]


@pytest.mark.asyncio
async def test_forward_to_target_url(client):
    """Test URL forwarding with redirect."""
    # Create URL
    create_response = await client.post(
        "/url",
        json={"target_url": "https://www.example.com"}
    )
    data = create_response.json()
    
    # Extract just the key from the full URL
    url_key = data["url"].split("/")[-1]
    
    # Test redirect
    response = await client.get(f"/{url_key}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://www.example.com"


@pytest.mark.asyncio
async def test_forward_updates_click_count(client):
    """Test that forwarding increments click counter."""
    # Create URL
    create_response = await client.post(
        "/url",
        json={"target_url": "https://www.example.com"}
    )
    data = create_response.json()
    
    # Extract key and secret from full URLs
    url_key = data["url"].split("/")[-1]
    secret_key = data["admin_url"].split("/")[-1]
    
    # Initial clicks should be 0
    assert data["clicks"] == 0
    
    # Click the shortened URL
    await client.get(f"/{url_key}", follow_redirects=False)
    
    # Check clicks incremented
    admin_response = await client.get(f"/admin/{secret_key}")
    assert admin_response.status_code == 200
    assert admin_response.json()["clicks"] == 1
    
    # Click again
    await client.get(f"/{url_key}", follow_redirects=False)
    admin_response = await client.get(f"/admin/{secret_key}")
    assert admin_response.json()["clicks"] == 2


@pytest.mark.asyncio
async def test_forward_nonexistent_url(client):
    """Test forwarding with non-existent key."""
    response = await client.get("/NOTEXIST")
    assert response.status_code == 404
    assert "doesn't exist" in response.json()["detail"]


@pytest.mark.asyncio
async def test_forward_inactive_url(client):
    """Test forwarding to deactivated URL returns 404."""
    # Create URL
    create_response = await client.post(
        "/url",
        json={"target_url": "https://www.example.com"}
    )
    data = create_response.json()
    
    url_key = data["url"].split("/")[-1]
    secret_key = data["admin_url"].split("/")[-1]
    
    # Delete it
    delete_response = await client.delete(f"/admin/{secret_key}")
    assert delete_response.status_code == 200
    
    # Try to access - should get 404
    response = await client.get(f"/{url_key}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_admin_info(client):
    """Test getting admin info for a URL."""
    # Create URL
    create_response = await client.post(
        "/url",
        json={"target_url": "https://www.example.com"}
    )
    data = create_response.json()
    secret_key = data["admin_url"].split("/")[-1]
    
    # Get admin info
    response = await client.get(f"/admin/{secret_key}")
    assert response.status_code == 200
    admin_data = response.json()
    assert admin_data["target_url"] == "https://www.example.com"
    assert admin_data["is_active"] is True
    assert admin_data["clicks"] == 0
    assert "url" in admin_data
    assert "admin_url" in admin_data


@pytest.mark.asyncio
async def test_get_admin_info_nonexistent(client):
    """Test getting admin info with invalid secret key."""
    response = await client.get("/admin/INVALIDSECRET_12345678")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_url(client):
    """Test deleting (deactivating) a URL."""
    # Create URL
    create_response = await client.post(
        "/url",
        json={"target_url": "https://www.example.com"}
    )
    data = create_response.json()
    secret_key = data["admin_url"].split("/")[-1]
    
    # Delete it
    response = await client.delete(f"/admin/{secret_key}")
    assert response.status_code == 200
    assert "Successfully deleted" in response.json()["detail"]
    assert "example.com" in response.json()["detail"]
    
    # Verify it's deactivated
    admin_response = await client.get(f"/admin/{secret_key}")
    assert admin_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_url(client):
    """Test deleting non-existent URL."""
    response = await client.delete("/admin/INVALIDSECRET_12345678")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_url_no_protocol(client):
    """Test URL creation without protocol."""
    response = await client.post(
        "/url",
        json={"target_url": "example.com"}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Test root endpoint returns welcome message."""
    response = await client.get("/")
    assert response.status_code == 200
    # Add a root endpoint to main.py if you don't have one


@pytest.mark.asyncio  
async def test_multiple_urls_same_target(client):
    """Test creating multiple shortened URLs for same target."""
    target = "https://www.example.com"
    
    # Create first URL
    response1 = await client.post("/url", json={"target_url": target})
    key1 = response1.json()["url"].split("/")[-1]
    
    # Create second URL for same target
    response2 = await client.post("/url", json={"target_url": target})
    key2 = response2.json()["url"].split("/")[-1]
    
    # Keys should be different
    assert key1 != key2
    
    # Both should forward to same target
    resp1 = await client.get(f"/{key1}", follow_redirects=False)
    resp2 = await client.get(f"/{key2}", follow_redirects=False)
    assert resp1.headers["location"] == target
    assert resp2.headers["location"] == target


@pytest.mark.asyncio
async def test_same_target_multiple_shortened_urls(client):
    """Test that same target URL can be shortened multiple times."""
    target = "https://popular-site.com"
    
    keys = []
    for _ in range(5):
        response = await client.post("/url", json={"target_url": target})
        keys.append(response.json()["url"].split("/")[-1])
    
    assert len(keys) == len(set(keys))
    
    for key in keys:
        response = await client.get(f"/{key}", follow_redirects=False)
        assert response.headers["location"] == target


@pytest.mark.asyncio
async def test_rapid_create_and_delete_cycle(client):
    """Test rapidly creating and deleting URLs."""
    for _ in range(10):
        create_resp = await client.post(
            "/url",
            json={"target_url": "https://example.com"}
        )
        secret = create_resp.json()["admin_url"].split("/")[-1]
        
        delete_resp = await client.delete(f"/admin/{secret}")
        assert delete_resp.status_code == 200


@pytest.mark.asyncio
async def test_deleted_url_stays_deleted(client):
    """Test that deleted URLs remain inaccessible."""
    create_resp = await client.post(
        "/url",
        json={"target_url": "https://example.com"}
    )
    data = create_resp.json()
    url_key = data["url"].split("/")[-1]
    secret = data["admin_url"].split("/")[-1]
    
    await client.delete(f"/admin/{secret}")
    
    for _ in range(5):
        response = await client.get(f"/{url_key}")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_extremely_long_url(client):
    """Test handling of very long URLs."""
    long_url = "https://example.com/" + "a" * 2000
    response = await client.post("/url", json={"target_url": long_url})
    assert response.status_code in [200, 400]


@pytest.mark.asyncio
async def test_url_with_unicode_characters(client):
    """Test URLs containing unicode characters."""
    unicode_url = "https://example.com/页面"
    response = await client.post("/url", json={"target_url": unicode_url})
    
    if response.status_code == 200:
        url_key = response.json()["url"].split("/")[-1]
        redirect_response = await client.get(f"/{url_key}", follow_redirects=False)
        assert redirect_response.status_code == 307


@pytest.mark.asyncio
async def test_url_with_query_parameters(client):
    """Test URLs with query parameters and fragments."""
    special_url = "https://example.com/page?param=value&other=123#section"
    response = await client.post("/url", json={"target_url": special_url})
    
    assert response.status_code == 200
    url_key = response.json()["url"].split("/")[-1]
    redirect_response = await client.get(f"/{url_key}", follow_redirects=False)
    assert redirect_response.headers["location"] == special_url


@pytest.mark.asyncio
async def test_empty_url(client):
    """Test creation with empty URL."""
    response = await client.post("/url", json={"target_url": ""})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_missing_url_field(client):
    """Test creation without target_url field."""
    response = await client.post("/url", json={})
    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_url_without_scheme(client):
    """Test URL without http/https."""
    response = await client.post("/url", json={"target_url": "example.com"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_javascript_url_scheme(client):
    """Test rejection of javascript: URLs."""
    response = await client.post("/url", json={"target_url": "javascript:alert('xss')"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_data_url_scheme(client):
    """Test rejection of data: URLs."""
    response = await client.post("/url", json={"target_url": "data:text/html,<script>alert('xss')</script>"})
    assert response.status_code == 400