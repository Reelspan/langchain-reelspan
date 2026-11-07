"""Runs the tools against a local stand-in for the API (no network)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Type

import pytest
from langchain_core.tools import BaseTool
from langchain_tests.unit_tests import ToolsUnitTests
from reelspan import Reelspan

from langchain_reelspan import ReelspanListProfiles, ReelspanPublishText, ReelspanPublishVideo, ReelspanToolkit

SEEN: list = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _record(self):
        n = int(self.headers.get("Content-Length") or 0)
        SEEN.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": self.rfile.read(n)})

    def do_GET(self):  # noqa: N802
        self._record()
        if self.headers.get("Authorization") != "Bearer rs_test":
            return self._reply(401, {"message": "Invalid API key", "error_code": "UNAUTHORIZED"})
        if self.path.startswith("/v1/profiles"):
            return self._reply(200, {"profiles": [{"username": "acme", "display_name": "Acme", "social_accounts": {"x": {"h": 1}, "tiktok": ""}}, {"username": "other", "social_accounts": {}}]})
        if self.path.startswith("/v1/posts/status"):
            return self._reply(200, {"status": "completed", "results": [{"platform": "x", "success": True, "url": "https://x.com/1", "raw": {"big": 1}}]})
        self._reply(404, {"message": "Not found", "error_code": "NOT_FOUND"})

    def do_POST(self):  # noqa: N802
        self._record()
        if self.path == "/v1/posts/text":
            return self._reply(202, {"success": True, "request_id": "req_1"})
        if self.path == "/v1/posts/video":
            return self._reply(202, {"success": True, "job_id": "job_1"})
        self._reply(404, {"message": "Not found"})


@pytest.fixture(scope="module")
def base():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def client(base):
    return Reelspan(api_key="rs_test", base_url=base)


def test_publish_text_waits_and_compacts(client):
    tool = ReelspanPublishText(client=client)
    out = tool.invoke({"profile": "acme", "platforms": ["x"], "caption": "Hello", "first_comment": "link"})
    assert out == {"request_id": "req_1", "status": "completed", "results": [{"platform": "x", "success": True, "url": "https://x.com/1"}]}
    sent = next(s for s in SEEN if s["path"] == "/v1/posts/text")
    body = json.loads(sent["body"])
    assert body["user"] == "acme" and body["platform"] == ["x"] and body["title"] == "Hello"
    assert body["first_comment"] == "link" and body["async_upload"] == "true"
    assert sent["headers"]["Idempotency-Key"]


def test_pinned_profile_wins(client):
    tool = ReelspanPublishVideo(client=client, profile="acme")
    out = tool.invoke({"profile": "other", "platforms": ["tiktok"], "video": "https://cdn.example.com/a.mp4", "scheduled_date": "2026-12-01T09:00:00Z"})
    assert out["job_id"] == "job_1"
    body = SEEN[-1]["body"].decode("latin1")
    assert 'name="user"\r\n\r\nacme' in body
    assert 'name="video"\r\n\r\nhttps://cdn.example.com/a.mp4' in body
    assert ReelspanListProfiles(client=client, profile="acme").invoke({}) == [{"username": "acme", "name": "Acme", "networks": ["x"]}]


def test_errors_go_back_to_the_model(client, base):
    out = ReelspanPublishText(client=client, allowed_platforms=["linkedin"]).invoke({"profile": "acme", "platforms": ["x"], "caption": "hi"})
    assert "Not allowed: x" in out
    bad = ReelspanListProfiles(client=Reelspan(api_key="nope", base_url=base)).invoke({})
    assert "401" in bad and "API key is invalid" in bad


def test_toolkit(client):
    names = {t.name for t in ReelspanToolkit(client=client).get_tools()}
    assert "reelspan_publish_video" in names and len(names) == 12
    ro = {t.name for t in ReelspanToolkit(client=client, read_only=True).get_tools()}
    assert not any(n.startswith("reelspan_publish") or n in ("reelspan_retry_post", "reelspan_cancel_scheduled_post") for n in ro)


class TestReelspanPublishTextStandard(ToolsUnitTests):
    """LangChain's standard checks for a tool."""

    @property
    def tool_constructor(self) -> Type[BaseTool]:
        return ReelspanPublishText

    @property
    def tool_constructor_params(self) -> dict:
        return {"client": Reelspan(api_key="rs_test", base_url="http://127.0.0.1:9")}

    @property
    def tool_invoke_params_example(self) -> dict:
        return {"profile": "acme", "platforms": ["x"], "caption": "Hello"}
