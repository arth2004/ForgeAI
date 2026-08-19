import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_organization_project_repository_lifecycle(client: AsyncClient):
    # 1. Register user
    user_payload = {
        "email": "lead@forgeai.dev",
        "password": "Password123!",
        "full_name": "Lead Architect",
        "organization_name": "Initial Org",
    }
    reg_resp = await client.post("/api/v1/auth/register", json=user_payload)
    assert reg_resp.status_code == 201
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. List organizations
    orgs_resp = await client.get("/api/v1/organizations", headers=headers)
    assert orgs_resp.status_code == 200
    orgs = orgs_resp.json()
    assert len(orgs) >= 1
    org_id = orgs[0]["id"]

    # 3. Create Project
    project_payload = {
        "name": "Core Banking System",
        "description": "High-throughput transaction processor",
        "organization_id": org_id,
        "settings": {"language": "python"},
    }
    proj_resp = await client.post("/api/v1/projects", json=project_payload, headers=headers)
    assert proj_resp.status_code == 201
    project_data = proj_resp.json()
    project_id = project_data["id"]
    assert project_data["name"] == "Core Banking System"

    # 4. Get Project by ID
    get_proj = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert get_proj.status_code == 200
    assert get_proj.json()["id"] == project_id

    # 5. Connect Repository
    repo_payload = {
        "project_id": project_id,
        "full_name": "org/core-banking",
        "default_branch": "main",
        "is_private": True,
    }
    repo_resp = await client.post(
        f"/api/v1/projects/{project_id}/repositories",
        json=repo_payload,
        headers=headers,
    )
    assert repo_resp.status_code == 201
    repo_data = repo_resp.json()
    assert repo_data["full_name"] == "org/core-banking"
    assert repo_data["indexing_status"] == "pending"

    # 6. List Repositories
    list_repo = await client.get(f"/api/v1/projects/{project_id}/repositories", headers=headers)
    assert list_repo.status_code == 200
    assert len(list_repo.json()) == 1


@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient):
    # User 1
    u1_reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "u1@tenant.com", "password": "Password123!", "organization_name": "Org 1"},
    )
    u1_token = u1_reg.json()["access_token"]
    u1_headers = {"Authorization": f"Bearer {u1_token}"}

    u1_orgs = (await client.get("/api/v1/organizations", headers=u1_headers)).json()
    u1_org_id = u1_orgs[0]["id"]

    # User 2
    u2_reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "u2@tenant.com", "password": "Password123!", "organization_name": "Org 2"},
    )
    u2_token = u2_reg.json()["access_token"]
    u2_headers = {"Authorization": f"Bearer {u2_token}"}

    # User 2 tries to create project in User 1's org -> forbidden
    forbidden_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Sneaky Project", "organization_id": u1_org_id},
        headers=u2_headers,
    )
    assert forbidden_resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_project_lifecycle_and_security(client: AsyncClient):
    # 1. Register User 1
    u1_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "owner@domain.com", "password": "Password123!", "organization_name": "Org Alpha"},
    )
    u1_token = u1_resp.json()["access_token"]
    u1_headers = {"Authorization": f"Bearer {u1_token}"}
    u1_org_id = (await client.get("/api/v1/organizations", headers=u1_headers)).json()[0]["id"]

    # Create project
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Alpha Project", "organization_id": u1_org_id},
        headers=u1_headers,
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # Connect a repository to the project
    repo_resp = await client.post(
        f"/api/v1/projects/{project_id}/repositories",
        json={"project_id": project_id, "full_name": "org-alpha/repo-1", "default_branch": "main"},
        headers=u1_headers,
    )
    assert repo_resp.status_code == 201

    # 2. Register User 2 (unauthorized tenant)
    u2_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "attacker@domain.com", "password": "Password123!", "organization_name": "Org Beta"},
    )
    u2_token = u2_resp.json()["access_token"]
    u2_headers = {"Authorization": f"Bearer {u2_token}"}

    # User 2 attempts to delete User 1's project -> 403 Forbidden
    del_forbidden = await client.delete(f"/api/v1/projects/{project_id}", headers=u2_headers)
    assert del_forbidden.status_code == 403

    # 3. User 1 successfully deletes project -> 200 OK
    del_success = await client.delete(f"/api/v1/projects/{project_id}", headers=u1_headers)
    assert del_success.status_code == 200
    assert del_success.json()["id"] == project_id

    # 4. Subsequent GET on deleted project returns 404 Not Found
    get_deleted = await client.get(f"/api/v1/projects/{project_id}", headers=u1_headers)
    assert get_deleted.status_code == 404

    # 5. Delete on non-existent project returns 404 Not Found
    import uuid
    random_id = str(uuid.uuid4())
    del_nonexistent = await client.delete(f"/api/v1/projects/{random_id}", headers=u1_headers)
    assert del_nonexistent.status_code == 404
