import json

import pytest
import requests

from lineage_service.datalens import client as client_module
from lineage_service.datalens.client import DataLensClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


def make_client(responses, calls, sleeps, max_retries=5):
    def fake_post(url, headers=None, json=None, verify=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json})
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkey_target = client_module.requests
    original = monkey_target.post
    monkey_target.post = fake_post  # тесты ниже восстанавливают через fixture

    return DataLensClient(
        org_id="org", get_token=lambda: "t1", refresh_token=lambda used: "t2",
        sleeper=sleeps.append, jitter=lambda: 0.0, max_retries=max_retries)


@pytest.fixture
def patch_post(monkeypatch):
    holders = {}

    def install(responses, calls):
        def fake_post(url, headers=None, json=None, verify=None, timeout=None):
            calls.append({"url": url, "headers": headers, "json": json})
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        holders["fn"] = fake_post
        monkeypatch.setattr(client_module.requests, "post", fake_post)
        return fake_post
    return install


def client_with(calls, sleeps, max_retries=5):
    return DataLensClient(org_id="org", get_token=lambda: "t1",
                          refresh_token=lambda used: "t2",
                          sleeper=sleeps.append, jitter=lambda: 0.0,
                          max_retries=max_retries)


def test_success_returns_json(patch_post):
    calls, sleeps = [], []
    patch_post([FakeResponse(200, {"ok": 1})], calls)
    assert client_with(calls, sleeps).req("/rpc/x", {}) == {"ok": 1}
    assert len(calls) == 1 and sleeps == []


def test_401_triggers_refresh_and_retry(patch_post):
    calls, sleeps = [], []
    patch_post([FakeResponse(401), FakeResponse(200, {"ok": 2})], calls)
    c = client_with(calls, sleeps)
    assert c.req("/rpc/x", {}) == {"ok": 2}
    assert calls[1]["headers"]["Authorization"] == "Bearer t2"
    assert c.token == "t2"


def test_429_respects_retry_after(patch_post):
    calls, sleeps = [], []
    patch_post([FakeResponse(429, headers={"Retry-After": "3"}), FakeResponse(200, {"ok": 3})], calls)
    assert client_with(calls, sleeps).req("/rpc/x", {}) == {"ok": 3}
    assert sleeps == [3.0]


def test_5xx_uses_exponential_backoff(patch_post):
    calls, sleeps = [], []
    patch_post([FakeResponse(503), FakeResponse(200, {"ok": 4})], calls)
    assert client_with(calls, sleeps).req("/rpc/x", {}) == {"ok": 4}
    assert sleeps == [1.0]  # 2**0 + jitter(0)


def test_4xx_returns_none_without_retry(patch_post):
    calls, sleeps = [], []
    patch_post([FakeResponse(400)], calls)
    assert client_with(calls, sleeps).req("/rpc/x", {}) is None
    assert len(calls) == 1 and sleeps == []


def test_network_error_retries(patch_post):
    calls, sleeps = [], []
    patch_post([requests.exceptions.ConnectionError("boom"), FakeResponse(200, {"ok": 5})], calls)
    assert client_with(calls, sleeps).req("/rpc/x", {}) == {"ok": 5}
    assert sleeps == [1.0]


def test_retries_exhausted_returns_none(patch_post):
    calls, sleeps = [], []
    patch_post([FakeResponse(429), FakeResponse(429)], calls)
    assert client_with(calls, sleeps, max_retries=2).req("/rpc/x", {}) is None
    assert len(calls) == 2 and sleeps == [1.0]


def test_entries_limit_pagination(patch_post):
    calls, sleeps = [], []
    patch_post([
        FakeResponse(200, {"entries": [{"entryId": "a"}], "nextPageToken": "tok"}),
        FakeResponse(200, {"entries": [{"entryId": "b"}]}),
    ], calls)
    c = client_with(calls, sleeps)
    assert [e["entryId"] for e in c.get_entries_limit("dataset")] == ["a", "b"]
    assert calls[1]["json"]["pageToken"] == "tok"


def test_entries_page_pagination(patch_post):
    calls, sleeps = [], []
    patch_post([
        FakeResponse(200, {"entries": [{"entryId": "a"}], "hasNextPage": True}),
        FakeResponse(200, {"entries": [{"entryId": "b"}], "hasNextPage": False}),
    ], calls)
    c = client_with(calls, sleeps)
    assert [e["entryId"] for e in c.get_entries_page("widget")] == ["a", "b"]
    assert calls[1]["json"]["page"] == 2


def test_relations_dedup(patch_post):
    calls, sleeps = [], []
    patch_post([FakeResponse(200, {"relations": [{"entryId": "x"}, {"entryId": "x"}, {"entryId": "y"}]})], calls)
    assert set(client_with(calls, sleeps).get_relations("d1", "to")) == {"x", "y"}