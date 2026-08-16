
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
