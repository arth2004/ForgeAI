import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_login_flow(client: AsyncClient):
    # 1. Register new user
    register_payload = {
        "email": "developer@forgeai.dev",
        "password": "SecurePassword123!",
        "full_name": "Dev User",
        "organization_name": "Acme Engineering",
    }
    response = await client.post("/api/v1/auth/register", json=register_payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    token = data["access_token"]

    # 2. Get /me with valid token
    headers = {"Authorization": f"Bearer {token}"}
    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    user_data = me_resp.json()
    assert user_data["email"] == "developer@forgeai.dev"
    assert user_data["full_name"] == "Dev User"
    assert user_data["is_active"] is True

    # 3. Duplicate registration should fail
    dup_resp = await client.post("/api/v1/auth/register", json=register_payload)
    assert dup_resp.status_code == 409

    # 4. Login with correct credentials
    login_payload = {
        "email": "developer@forgeai.dev",
        "password": "SecurePassword123!",
    }
    login_resp = await client.post("/api/v1/auth/login", json=login_payload)
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()

    # 5. Login with invalid password
    bad_login = {
        "email": "developer@forgeai.dev",
        "password": "WrongPassword!",
    }
    bad_resp = await client.post("/api/v1/auth/login", json=bad_login)
    assert bad_resp.status_code == 401


@pytest.mark.asyncio
async def test_unauthorized_access(client: AsyncClient):
    # Missing token
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in [400, 401, 422]

    # Invalid token
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token"})
    assert resp.status_code == 401
