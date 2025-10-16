import pytest

@pytest.mark.asyncio
async def test_create_url_success(client):
    response = await client.post("/url", json={"target_url": "https://example.com"})
    assert response.status_code == 200
    assert response.json()["target_url"] == "https://example.com"


@pytest.mark.asyncio
async def test_create_url_invalid(client):
    response = await client.post("/url", json={"target_url": "invalid"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_url_redirect(client):
    # Create URL
    create_resp = await client.post("/url", json={"target_url": "https://example.com"})
    key = create_resp.json()["url"]
    
    # Test redirect
    redirect_resp = await client.get(f"/{key}", follow_redirects=False)
    assert redirect_resp.status_code == 307


@pytest.mark.asyncio
async def test_admin_info(client):
    # Create URL
    create_resp = await client.post("/url", json={"target_url": "https://example.com"})
    secret_key = create_resp.json()["admin_url"]
    
    # Get admin info
    admin_resp = await client.get(f"/admin/{secret_key}")
    assert admin_resp.status_code == 200
    assert admin_resp.json()["clicks"] == 0


@pytest.mark.asyncio
async def test_delete_url(client):
    # Create URL
    create_resp = await client.post("/url", json={"target_url": "https://example.com"})
    secret_key = create_resp.json()["admin_url"]
    
    # Delete it
    delete_resp = await client.delete(f"/admin/{secret_key}")
    assert delete_resp.status_code == 200
    
    # Verify it's inactive
    admin_resp = await client.get(f"/admin/{secret_key}")
    assert admin_resp.status_code == 404
