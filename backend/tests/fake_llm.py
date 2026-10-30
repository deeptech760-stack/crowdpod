"""A tiny model server for tests. It speaks both the OpenAI-compatible and the Anthropic
Messages API shapes and answers like a model would, with fixed content."""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _answer(system: str, user: str) -> str:
    if '{"ok": true}' in system:
        return '{"ok": true}'
    if "panel of separate, real people" in system:
        ids = re.findall(r"^\[([^\]]+)\]", user, flags=re.MULTILINE)
        verdicts = ["adopt", "maybe", "reject"]
        return json.dumps({"reactions": [
            {"persona_id": pid, "verdict": verdicts[i % 3], "willingness_to_pay": 100 * (i % 3 == 0),
             "sentiment": 0.5 - 0.5 * (i % 3), "quote": f"Fake quote {i}", "top_objection": "Fake objection",
             "must_have": "Fake feature", "reasoning": "Fake reasoning"}
            for i, pid in enumerate(ids)
        ]})
    if "You are using a website" in user:
        return json.dumps({"thought": "Nothing here for me.", "action": "give_up", "target": "", "text": ""})
    if "product architect" in system:
        return "# Doc from fake model\n\n## Ask real people next\n1. Fake question"
    return "Fake answer"


class FakeLLM:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def _send(self, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                path = self.path.split("?")[0].rstrip("/")
                if path == "/v1/models" and self.headers.get("anthropic-version"):  # Anthropic shape
                    self._send({"data": [{"id": "claude-opus-5-5", "type": "model", "display_name": "Claude Opus 5.5",
                                          "created_at": "2026-01-01T00:00:00Z"}],
                                "has_more": False, "first_id": "claude-opus-5-5", "last_id": "claude-opus-5-5"})
                elif path.endswith("/models"):
                    self._send({"object": "list", "data": [
                        {"id": "fake-small", "object": "model", "created": 0, "owned_by": "test"}]})
                else:
                    self.send_error(404)

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                path = self.path.split("?")[0]
                if path == "/v1/messages":  # Anthropic Messages API
                    key = self.headers.get("x-api-key") or (self.headers.get("Authorization") or "").removeprefix("Bearer ")
                    outer.requests.append({"auth": key, "path": self.path,
                                           "beta": self.headers.get("anthropic-beta"), "body": body})
                    content = _answer(body.get("system", ""), body["messages"][0]["content"])
                    self._send({
                        "id": "msg_fake", "type": "message", "role": "assistant", "model": body["model"],
                        "content": [{"type": "text", "text": content}], "stop_reason": "end_turn",
                        "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
                    })
                    return
                outer.requests.append({"auth": self.headers.get("Authorization"), "body": body})
                msgs = body["messages"]
                content = _answer(msgs[0]["content"], msgs[1]["content"])
                self._send({
                    "id": "chatcmpl-fake", "object": "chat.completion", "created": 0, "model": body["model"],
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                })

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.root = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.base_url = f"{self.root}/v1"  # OpenAI-compatible clients take the /v1 prefix
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
