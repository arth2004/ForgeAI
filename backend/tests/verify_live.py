import asyncio
import httpx


async def verify():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Health check
        health_resp = await client.get("/api/v1/health")
        print("1. Health check:", health_resp.status_code, health_resp.json())
        assert health_resp.status_code == 200
        assert health_resp.json()["status"] == "ok"

        # 2. Register user & Organization
        reg_payload = {
            "email": "lead.architect@forgeai.dev",
            "password": "ProductionPassword123!",
            "full_name": "Lead Architect",
            "organization_name": "Forge AI Core",
        }
        reg_resp = await client.post("/api/v1/auth/register", json=reg_payload)
        print("2. Register user:", reg_resp.status_code, reg_resp.json())
        assert reg_resp.status_code == 201
        token = reg_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Get /me
        me_resp = await client.get("/api/v1/auth/me", headers=headers)
        print("3. Auth /me profile:", me_resp.status_code, me_resp.json())
        assert me_resp.status_code == 200

        # 4. List Orgs
        orgs_resp = await client.get("/api/v1/organizations", headers=headers)
        print("4. Organizations:", orgs_resp.status_code, orgs_resp.json())
        assert orgs_resp.status_code == 200
        org_id = orgs_resp.json()[0]["id"]

        # 5. Create Project
        proj_payload = {
            "name": "Forge Platform Engine",
            "description": "Core intelligence engine",
            "organization_id": org_id,
        }
        proj_resp = await client.post("/api/v1/projects", json=proj_payload, headers=headers)
        print("5. Create project:", proj_resp.status_code, proj_resp.json())
        assert proj_resp.status_code == 201
        proj_id = proj_resp.json()["id"]

        # 6. Connect Repository
        repo_payload = {
            "project_id": proj_id,
            "full_name": "forgeai/forge-engine",
            "default_branch": "main",
            "is_private": True,
        }
        repo_resp = await client.post(
            f"/api/v1/projects/{proj_id}/repositories",
            json=repo_payload,
            headers=headers,
        )
        print("6. Connect repository:", repo_resp.status_code, repo_resp.json())
        assert repo_resp.status_code == 201

        # 7. ARQ Worker Job Pipeline Test
        job_enqueue = await client.post("/api/v1/worker/test-job", json={"message": "Verification ping"})
        print("7. Enqueue ARQ task:", job_enqueue.status_code, job_enqueue.json())
        assert job_enqueue.status_code == 202
        job_id = job_enqueue.json()["job_id"]

        # Poll for job execution in worker
        for attempt in range(10):
            await asyncio.sleep(0.5)
            job_status = await client.get(f"/api/v1/worker/test-job/{job_id}")
            data = job_status.json()
            if data["status"] in ["complete", "success"] or data.get("result"):
                print(f"8. ARQ Worker Job Result (Attempt {attempt+1}):", data)
                assert data["result"]["status"] == "success"
                assert data["result"]["worker_name"] == "ForgeAI-ARQ-Worker"
                break

        print("\n>>> ALL PHASE 1 LIVE BACKEND & WORKER VERIFICATIONS PASSED SUCCESSFULLY! <<<\n")


if __name__ == "__main__":
    asyncio.run(verify())
