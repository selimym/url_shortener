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