from typing import Any

from arq.jobs import Job
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.redis import get_arq_pool

router = APIRouter(prefix="/worker", tags=["Worker"])


class JobEnqueueRequest(BaseModel):
    message: str = "ping"


class JobEnqueueResponse(BaseModel):
    job_id: str
    status: str = "queued"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Any = None


@router.post("/test-job", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_test_job(request: JobEnqueueRequest = JobEnqueueRequest()):
    """Enqueue a health check test job to the ARQ Redis queue."""
    arq_pool = await get_arq_pool()
    job = await arq_pool.enqueue_job("health_check_job", {"message": request.message})
    if not job:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue test job to ARQ queue.",
        )
    return JobEnqueueResponse(job_id=job.job_id, status="queued")


@router.get("/test-job/{job_id}", response_model=JobStatusResponse)
async def get_test_job_status(job_id: str):
    """Check status and retrieve result of an ARQ worker job."""
    arq_pool = await get_arq_pool()
    job = Job(job_id=job_id, redis=arq_pool)
    job_status = await job.status()

    result = None
    if job_status.value in ["complete", "success"]:
        result = await job.result()

    return JobStatusResponse(
        job_id=job_id,
        status=job_status.value,
        result=result,
    )
