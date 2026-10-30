"""The MCP server, exercised the way Claude Code or Codex would: a real stdio session."""

from __future__ import annotations

import asyncio
import json
import socket
import sys
import threading
import time

import pytest
import uvicorn
from mcp import ClientSession, StdioServerParameters, stdio_client

from crowdpod.api import create_app

EXPECTED_TOOLS = {
    "list_personas", "start_simulation", "get_results", "get_documents", "get_browser_sessions",
    "interview_persona", "visit_as_persona", "browser_step", "end_visit",
}


@pytest.fixture
def api_url(settings):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(5)


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


async def test_mcp_session_end_to_end(settings, api_url, site_url, brief):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "crowdpod.cli", "mcp"],
        env={"CROWDPOD_API_URL": api_url, "CROWDPOD_DATA_DIR": str(settings.data_dir)},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = {t.name for t in (await session.list_tools()).tools}
        assert tools == EXPECTED_TOOLS

        assert "mother" in _text(await session.call_tool("list_personas", {}))

        started = _text(await session.call_tool("start_simulation", {
            "name": brief.name, "idea": brief.pitch, "price": brief.price, "crowd_size": 40,
        }))
        run_id = started.split("run ")[1].split(".")[0]
        for _ in range(100):
            results = _text(await session.call_tool("get_results", {"run_id": run_id}))
            if "finished" in results:
                break
            await asyncio.sleep(0.2)
        assert "Segments:" in results and "Adopt" in results
        assert _text(await session.call_tool("get_documents", {"run_id": run_id})).startswith("# Business Requirements")

        # a live visit: the test plays the client's model and chooses the clicks
        opened = await session.call_tool("visit_as_persona", {
            "url": f"{site_url}/fitdesk-cluttered/", "goal": "find the price", "persona": "corporate-worker",
        })
        brief_text = _text(opened)
        assert "You are now playing this person" in brief_text and "<<<PAGE" in brief_text
        assert any(c.type == "image" for c in opened.content)
        visit_id = brief_text.split("Visit ")[1].split(".")[0]
        link = next(line for line in brief_text.splitlines() if '"Integrations"' in line).split(":")[0].strip("- ")
        stepped = _text(await session.call_tool("browser_step", {
            "visit_id": visit_id, "action": "click", "target": link, "thought": "Does it sync with my calendar?",
        }))
        assert "Error" not in stepped and "Outlook calendar sync" in stepped

        bad = await session.call_tool("visit_as_persona", {"url": "file:///C:/Windows/win.ini", "goal": "x"})
        assert bad.is_error

        closed = _text(await session.call_tool("end_visit", {
            "visit_id": visit_id, "outcome": "success", "summary": "Found the calendar sync.",
        }))
        assert "success after 1 steps" in closed

    log = json.loads((settings.data_dir / "mcp-visits" / f"{visit_id}.json").read_text(encoding="utf-8"))
    assert log["steps"][0]["target_label"] == "Integrations" and log["outcome"] == "success"
