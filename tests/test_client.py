"""A2A client integration test.

Start the server first: uv run python -m app
Then run: uv run pytest tests/test_client.py
"""

import httpx
import pytest


@pytest.fixture
def base_url():
    return "http://localhost:10000"


@pytest.mark.asyncio
async def test_agent_card(base_url: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}/.well-known/agent.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card["name"] == "Research Agent"
        assert len(card["skills"]) > 0


@pytest.mark.asyncio
async def test_message_send(base_url: str):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "msg-001",
                "role": "user",
                "parts": [{"kind": "text", "text": "What is quantum computing?"}],
            }
        },
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{base_url}/", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        result = data["result"]
        assert result["status"]["state"] == "completed"
        assert len(result["artifacts"]) > 0
        report_text = result["artifacts"][0]["parts"][0]["text"]
        assert len(report_text) > 100
