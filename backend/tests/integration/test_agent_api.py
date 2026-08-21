import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import build_agent_graph
from app.agent.models import MockChatModelProvider
from app.core.security import hash_password
from app.models.agent import AgentSession
from app.models.auth import Organization, User
from app.models.project import IndexingStatus, Project, Repository


def _make_graph_builder(provider: MockChatModelProvider):
    """Helper creating a bound build_agent_graph override preventing duplicate kwarg errors."""

    def _builder(**kwargs):
        kwargs.pop("model_provider", None)
        return build_agent_graph(model_provider=provider, **kwargs)

    return _builder


@pytest.mark.asyncio
async def test_agent_chat_unauthenticated_rejected(client: AsyncClient, indexed_tool_repo):
    """Verifies that requests lacking valid Bearer credentials return 401 Unauthorized."""
    project = indexed_tool_repo["project"]
    payload = {
        "message": "Where is the parser implemented?",
        "project_id": str(project.id),
    }
    response = await client.post("/api/v1/agent/chat", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_agent_chat_unauthorized_project_forbidden(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
):
    """Verifies that an authenticated user cannot execute queries against a project they don't belong to."""
    other_org = Organization(name="Other Org", slug="other-org")
    db_session.add(other_org)
    await db_session.flush()

    other_project = Project(
        organization_id=other_org.id,
        name="Private Project",
        description="Private",
    )
    db_session.add(other_project)
    await db_session.commit()

    payload = {
        "message": "What is in this project?",
        "project_id": str(other_project.id),
    }
    response = await client.post("/api/v1/agent/chat", json=payload, headers=auth_headers)
    assert response.status_code == 403
    assert "access to this project" in response.json()["message"]


@pytest.mark.asyncio
async def test_agent_chat_mismatched_repository_conflict(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    indexed_tool_repo,
):
    """Verifies that supplying a repository ID that belongs to another project returns 409 Conflict."""
    project = indexed_tool_repo["project"]

    other_org = Organization(name="Second Org", slug="second-org")
    db_session.add(other_org)
    await db_session.flush()

    other_project = Project(organization_id=other_org.id, name="P2")
    db_session.add(other_project)
    await db_session.flush()

    foreign_repo = Repository(
        project_id=other_project.id,
        github_repo_id=112233,
        owner="foreign",
        full_name="foreign/repo",
        default_branch="main",
        indexing_status=IndexingStatus.ready,
    )
    db_session.add(foreign_repo)
    await db_session.commit()

    payload = {
        "message": "Explain foreign repo",
        "project_id": str(project.id),
        "repository_id": str(foreign_repo.id),
    }
    response = await client.post("/api/v1/agent/chat", json=payload, headers=auth_headers)
    assert response.status_code == 409
    assert "belongs to another project" in response.json()["message"]


@pytest.mark.asyncio
async def test_agent_chat_direct_answer_non_streaming(
    client: AsyncClient, auth_headers: dict[str, str], indexed_tool_repo
):
    """Verifies full non-streaming direct answer path through the API."""
    project = indexed_tool_repo["project"]
    direct_answer = AIMessage(
        content="Forge AI is a repository reasoning engine powered by LangGraph."
    )
    mock_provider = MockChatModelProvider(responses=[direct_answer])

    payload = {
        "message": "What is Forge AI?",
        "project_id": str(project.id),
    }

    with patch("app.services.agent_service.build_agent_graph") as mock_build_graph:
        mock_build_graph.side_effect = _make_graph_builder(mock_provider)
        response = await client.post("/api/v1/agent/chat", json=payload, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == direct_answer.content
    assert data["project_id"] == str(project.id)
    assert data["session_id"] is not None
    assert data["metadata"]["iterations"] == 1
    assert data["metadata"]["tool_calls"] == 0
    assert data["metadata"]["duration_ms"] > 0
    assert len(data["sources"]) == 0


@pytest.mark.asyncio
async def test_agent_chat_repository_tool_use_with_grounded_sources(
    client: AsyncClient, auth_headers: dict[str, str], indexed_tool_repo
):
    """Verifies end-to-end repository tool execution via API with citation sources."""
    project = indexed_tool_repo["project"]

    step1_tool = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_repository",
                "args": {
                    "query": "Where are embeddings generated?",
                    "project_id": str(project.id),
                },
                "id": "call_search_api",
            }
        ],
    )
    step2_ans = AIMessage(
        content="Embeddings are generated in `backend/app/services/embedding/gemini.py`."
    )
    mock_provider = MockChatModelProvider(responses=[step1_tool, step2_ans])

    payload = {
        "message": "Where are embeddings generated?",
        "project_id": str(project.id),
    }

    query_vec = [0.0] * 768
    query_vec[0] = 1.0

    with (
        patch("app.services.agent_service.build_agent_graph") as mock_build_graph,
        patch(
            "app.services.embedding.gemini.GeminiEmbeddingProvider.embed_query",
            new_callable=AsyncMock,
            return_value=query_vec,
        ),
    ):
        mock_build_graph.side_effect = _make_graph_builder(mock_provider)
        response = await client.post("/api/v1/agent/chat", json=payload, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == step2_ans.content
    assert data["metadata"]["tool_calls"] == 1
    assert len(data["sources"]) > 0
    assert any("gemini.py" in s["file_path"] for s in data["sources"])


@pytest.mark.asyncio
async def test_agent_chat_creates_and_reuses_session(
    client: AsyncClient, auth_headers: dict[str, str], indexed_tool_repo
):
    """Verifies session context persistence and reuse across multiple chat turns."""
    project = indexed_tool_repo["project"]
    mock_provider = MockChatModelProvider(default_response="Turn response.")

    with patch("app.services.agent_service.build_agent_graph") as mock_build_graph:
        mock_build_graph.side_effect = _make_graph_builder(mock_provider)

        # Turn 1: Create session
        res1 = await client.post(
            "/api/v1/agent/chat",
            json={"message": "First message", "project_id": str(project.id)},
            headers=auth_headers,
        )
        assert res1.status_code == 200
        session_id = res1.json()["session_id"]
        assert session_id is not None

        # Turn 2: Reuse session
        res2 = await client.post(
            "/api/v1/agent/chat",
            json={
                "message": "Second message",
                "project_id": str(project.id),
                "session_id": session_id,
            },
            headers=auth_headers,
        )
        assert res2.status_code == 200
        assert res2.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_agent_chat_session_ownership_enforced(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    indexed_tool_repo,
):
    """Verifies that User B cannot use a session ID owned by User A."""
    project = indexed_tool_repo["project"]
    repo = indexed_tool_repo["repository"]

    user_b = User(
        email="user_b@forge.ai",
        hashed_password=hash_password("Password123!"),
        full_name="User B",
        is_active=True,
    )
    db_session.add(user_b)
    await db_session.flush()

    session_b = AgentSession(
        user_id=user_b.id,
        project_id=project.id,
        repository_id=repo.id,
    )
    db_session.add(session_b)
    await db_session.commit()

    # User A (auth_headers) tries to use session_b
    response = await client.post(
        "/api/v1/agent/chat",
        json={
            "message": "Steal session",
            "project_id": str(project.id),
            "session_id": str(session_b.id),
        },
        headers=auth_headers,
    )
    assert response.status_code == 403
    assert "access to this agent session" in response.json()["message"]


@pytest.mark.asyncio
async def test_agent_chat_session_context_mismatch_rejected(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: AsyncSession,
    indexed_tool_repo,
):
    """Verifies that reusing a session with a mismatched project or repository ID returns 409 Conflict."""
    project = indexed_tool_repo["project"]
    repo = indexed_tool_repo["repository"]

    session = AgentSession(
        user_id=test_user.id,
        project_id=project.id,
        repository_id=repo.id,
    )
    db_session.add(session)
    await db_session.commit()

    # Request with a different repository ID
    random_repo_id = str(uuid.uuid4())
    res_mismatch_repo = await client.post(
        "/api/v1/agent/chat",
        json={
            "message": "Mismatch repo",
            "project_id": str(project.id),
            "repository_id": random_repo_id,
            "session_id": str(session.id),
        },
        headers=auth_headers,
    )
    assert res_mismatch_repo.status_code == 409
    assert "is bound to repository" in res_mismatch_repo.json()["message"]


@pytest.mark.asyncio
async def test_agent_chat_sse_streaming_direct_endpoint(
    client: AsyncClient, auth_headers: dict[str, str], indexed_tool_repo
):
    """Verifies Server-Sent Events (SSE) streaming chat endpoint."""
    project = indexed_tool_repo["project"]
    direct_ans = AIMessage(content="Streaming answer.")
    mock_provider = MockChatModelProvider(responses=[direct_ans])

    payload = {
        "message": "Stream test",
        "project_id": str(project.id),
    }

    with patch("app.services.agent_service.build_agent_graph") as mock_build_graph:
        mock_build_graph.side_effect = _make_graph_builder(mock_provider)

        response = await client.post(
            "/api/v1/agent/chat/stream", json=payload, headers=auth_headers
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    body_text = response.text
    assert "event: session.created" in body_text
    assert "event: agent.started" in body_text
    assert "event: agent.completed" in body_text
    assert "Streaming answer." in body_text


@pytest.mark.asyncio
async def test_agent_chat_sse_streaming_with_tool_lifecycle(
    client: AsyncClient, auth_headers: dict[str, str], indexed_tool_repo
):
    """Verifies SSE streaming emits agent.tool_call and agent.tool_result events."""
    project = indexed_tool_repo["project"]

    step1_tool = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_symbol",
                "args": {
                    "symbol_name": "HybridSearchEngine",
                    "project_id": str(project.id),
                },
                "id": "sse_call_sym",
            }
        ],
    )
    step2_ans = AIMessage(content="Located HybridSearchEngine symbol.")
    mock_provider = MockChatModelProvider(responses=[step1_tool, step2_ans])

    payload = {
        "message": "Find HybridSearchEngine",
        "project_id": str(project.id),
        "stream": True,
    }

    with patch("app.services.agent_service.build_agent_graph") as mock_build_graph:
        mock_build_graph.side_effect = _make_graph_builder(mock_provider)

        response = await client.post("/api/v1/agent/chat", json=payload, headers=auth_headers)

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    body_text = response.text
    assert "event: session.created" in body_text
    assert "event: agent.started" in body_text
    assert "event: agent.tool_call" in body_text
    assert "search_symbol" in body_text
    assert "event: agent.tool_result" in body_text
    assert "event: agent.completed" in body_text


@pytest.mark.asyncio
async def test_agent_chat_validation_errors(
    client: AsyncClient, auth_headers: dict[str, str], indexed_tool_repo
):
    """Verifies that invalid payloads are rejected with 422 Unprocessable Entity."""
    project = indexed_tool_repo["project"]

    # 1. Empty message
    res_empty = await client.post(
        "/api/v1/agent/chat",
        json={"message": "", "project_id": str(project.id)},
        headers=auth_headers,
    )
    assert res_empty.status_code == 422

    # 2. Oversized message (>4000 chars)
    res_oversized = await client.post(
        "/api/v1/agent/chat",
        json={"message": "a" * 4001, "project_id": str(project.id)},
        headers=auth_headers,
    )
    assert res_oversized.status_code == 422


@pytest.mark.asyncio
async def test_agent_chat_timeout_handling(
    client: AsyncClient, auth_headers: dict[str, str], indexed_tool_repo
):
    """Verifies that an execution timeout returns 504 Gateway Timeout."""
    project = indexed_tool_repo["project"]

    payload = {
        "message": "Long query",
        "project_id": str(project.id),
    }

    with (
        patch(
            "app.services.agent_service.settings.AGENT_TIMEOUT_SECONDS",
            0.001,
        ),
        patch("app.services.agent_service.build_agent_graph") as mock_build_graph,
    ):

        async def _slow_ainvoke(*args, **kwargs):
            import asyncio

            await asyncio.sleep(0.05)
            return {}

        mock_graph = AsyncMock()
        mock_graph.ainvoke = _slow_ainvoke
        mock_build_graph.return_value = mock_graph

        response = await client.post("/api/v1/agent/chat", json=payload, headers=auth_headers)

    assert response.status_code == 504
    assert "timeout limit" in response.json()["message"]
