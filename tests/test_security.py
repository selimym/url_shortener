import pytest

@pytest.mark.asyncio
async def test_path_traversal_in_secret_key(client):
    """Test that path traversal attempts in secret key are rejected.

    Note: ".." alone is excluded because httpx normalizes /admin/.. to /
    per RFC 3986 before it reaches the server. Our regex validation handles
    ".." for direct HTTP clients that bypass client-side normalization.
    """
    malicious_keys = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
        "./secret",
    ]

    for key in malicious_keys:
        response = await client.get(f"/admin/{key}")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_xss_in_secret_key(client):
    """Test that XSS attempts in secret key don't cause issues."""
    xss_payloads = [
        "<script>alert('xss')</script>",
        "javascript:alert('xss')",
        "<img src=x onerror=alert('xss')>",
    ]
    
    for payload in xss_payloads:
        response = await client.get(f"/admin/{payload}")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_sql_injection_in_url_key(client):
    """Test that SQL injection attempts are handled safely."""
    sql_payloads = [
        "' OR '1'='1",
        "1' UNION SELECT * FROM users--",
        "'; DROP TABLE urls;--",
    ]
    
    for payload in sql_payloads:
        response = await client.get(f"/{payload}")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_extremely_long_secret_key(client):
    """Test handling of abnormally long secret keys."""
    long_key = "A" * 10000
    response = await client.get(f"/admin/{long_key}")
    assert response.status_code == 404
