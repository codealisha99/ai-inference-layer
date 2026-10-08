import threading

import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.ratelimit import RateLimiter
from src.server import build_app


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


class TestTokenBucket:
    def test_allows_up_to_burst_then_blocks(self, clock):
        rl = RateLimiter(60, burst=3, clock=clock)
        results = [rl.check("a").allowed for _ in range(5)]
        assert results == [True, True, True, False, False]

    def test_remaining_counts_down(self, clock):
        rl = RateLimiter(60, burst=3, clock=clock)
        assert [rl.check("a").remaining for _ in range(3)] == [2, 1, 0]

    def test_refills_at_the_configured_rate(self, clock):
        rl = RateLimiter(60, burst=2, clock=clock)  # 1 token per second
        rl.check("a")
        rl.check("a")
        assert not rl.check("a").allowed
        clock.advance(1.0)
        assert rl.check("a").allowed
        assert not rl.check("a").allowed

    def test_refill_is_capped_at_burst(self, clock):
        rl = RateLimiter(60, burst=2, clock=clock)
        rl.check("a")
        clock.advance(3600)
        assert [rl.check("a").allowed for _ in range(3)] == [True, True, False]

    def test_retry_after_is_time_to_next_token(self, clock):
        rl = RateLimiter(30, burst=1, clock=clock)  # one token every 2 seconds
        rl.check("a")
        blocked = rl.check("a")
        assert not blocked.allowed
        assert blocked.retry_after == 2
        clock.advance(1.0)
        assert rl.check("a").retry_after == 1

    def test_allowed_decisions_have_no_retry_after(self, clock):
        assert RateLimiter(60, burst=5, clock=clock).check("a").retry_after == 0

    def test_reset_is_time_until_full(self, clock):
        rl = RateLimiter(60, burst=4, clock=clock)
        assert rl.check("a").reset == 1  # one token spent -> one second to refill
        assert rl.check("a").reset == 2

    def test_clients_are_independent(self, clock):
        rl = RateLimiter(60, burst=1, clock=clock)
        assert rl.check("a").allowed
        assert not rl.check("a").allowed
        assert rl.check("b").allowed

    def test_default_burst_equals_rate(self, clock):
        rl = RateLimiter(5, clock=clock)
        assert [rl.check("a").allowed for _ in range(6)] == [True] * 5 + [False]

    @pytest.mark.parametrize("kwargs", [{"per_minute": 0}, {"per_minute": 5, "burst": 0}])
    def test_invalid_configuration(self, kwargs):
        with pytest.raises(ValueError):
            RateLimiter(**kwargs)

    def test_memory_is_bounded_by_dropping_idle_clients_first(self, clock):
        rl = RateLimiter(60, burst=1, max_clients=3, clock=clock)
        rl.check("old1")
        rl.check("old2")
        clock.advance(10)  # both are full again, so they are idle
        rl.check("busy1")
        rl.check("busy2")
        assert len(rl) == 3
        assert not rl.check("busy1").allowed  # active clients keep their state

    def test_memory_is_bounded_even_when_every_client_is_active(self, clock):
        rl = RateLimiter(60, burst=1, max_clients=50, clock=clock)
        for n in range(500):
            rl.check(f"c{n}")
        assert len(rl) == 50

    def test_thread_safe_total_matches_burst(self):
        rl = RateLimiter(1, burst=100)  # refill is negligible during the test
        allowed = []

        def hammer():
            allowed.extend(rl.check("shared").allowed for _ in range(50))

        threads = [threading.Thread(target=hammer) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert allowed.count(True) == 100
        assert len(allowed) == 400


def _app(**kw):
    return TestClient(build_app(settings=Settings(**kw)))


class TestHttpIntegration:
    def test_disabled_by_default(self):
        with _app() as c:
            assert all(c.get("/models").status_code == 200 for _ in range(30))
            assert "x-ratelimit-limit" not in c.get("/models").headers

    def test_blocks_after_the_burst_with_headers(self):
        with _app(rate_limit_per_minute=1, rate_limit_burst=3) as c:
            codes = [c.get("/models").status_code for _ in range(5)]
            r = c.get("/models")
        assert codes == [200, 200, 200, 429, 429]
        assert r.status_code == 429
        assert r.json() == {"success": False, "data": None, "error": "rate limit exceeded"}
        assert int(r.headers["retry-after"]) >= 1
        assert r.headers["x-ratelimit-limit"] == "3"
        assert r.headers["x-ratelimit-remaining"] == "0"
        assert r.headers["x-content-type-options"] == "nosniff"  # still a full response

    def test_success_responses_report_remaining_quota(self):
        with _app(rate_limit_per_minute=1, rate_limit_burst=5) as c:
            remaining = [c.get("/models").headers["x-ratelimit-remaining"] for _ in range(3)]
        assert remaining == ["4", "3", "2"]

    def test_probes_docs_landing_and_metrics_are_exempt(self):
        with _app(rate_limit_per_minute=1, rate_limit_burst=1) as c:
            c.get("/models")
            assert c.get("/models").status_code == 429
            for path in ("/health", "/livez", "/readyz", "/metrics", "/openapi.json", "/"):
                for _ in range(3):
                    assert c.get(path).status_code == 200, path

    def test_applies_to_every_api_route(self):
        with _app(rate_limit_per_minute=1, rate_limit_burst=1) as c:
            c.get("/models")
            assert c.post("/models", json={"name": "a", "type": "embedding"}).status_code == 429
            assert c.delete("/models/x").status_code == 429
            assert c.get("/nope").status_code == 429

    def test_limited_before_authentication(self):
        """Wrong-key guesses must burn quota, otherwise keys could be brute-forced."""
        with _app(rate_limit_per_minute=1, rate_limit_burst=2, api_key="s3cret") as c:
            codes = [
                c.get("/models", headers={"x-api-key": f"guess{n}"}).status_code for n in range(4)
            ]
        assert codes == [401, 401, 429, 429]

    def test_429s_are_counted_in_metrics(self):
        with _app(rate_limit_per_minute=1, rate_limit_burst=1) as c:
            c.get("/models")
            c.get("/models")
            assert 'status="429"' in c.get("/metrics").text

    def test_options_preflight_is_not_limited(self):
        with _app(
            rate_limit_per_minute=1, rate_limit_burst=1, cors_origins=("https://a.example",)
        ) as c:
            c.get("/models")
            r = c.options(
                "/models",
                headers={"origin": "https://a.example", "access-control-request-method": "GET"},
            )
        assert r.status_code == 200

    def test_streaming_and_batch_consume_one_request_each(self):
        with _app(rate_limit_per_minute=1, rate_limit_burst=4) as c:
            mid = c.post("/models", json={"name": "g", "type": "text-generation"}).json()["data"][
                "id"
            ]
            assert (
                c.post(f"/models/{mid}/infer/batch", json={"inputs": ["a"] * 10}).status_code == 201
            )
            assert c.post(f"/models/{mid}/infer/stream", json={"input": "x"}).status_code == 200
            assert c.get(f"/models/{mid}").status_code == 200
            assert c.get(f"/models/{mid}").status_code == 429


class TestClientIdentity:
    def test_default_ignores_forwarded_for(self):
        """Without TRUST_PROXY a client cannot dodge the limit by spoofing the header."""
        with _app(rate_limit_per_minute=1, rate_limit_burst=1) as c:
            assert c.get("/models", headers={"x-forwarded-for": "1.1.1.1"}).status_code == 200
            assert c.get("/models", headers={"x-forwarded-for": "2.2.2.2"}).status_code == 429

    def test_trust_proxy_keys_on_the_last_hop(self):
        with _app(rate_limit_per_minute=1, rate_limit_burst=1, trust_proxy=True) as c:
            hdr = lambda xff: {"x-forwarded-for": xff}  # noqa: E731
            assert c.get("/models", headers=hdr("9.9.9.9, 10.0.0.1")).status_code == 200
            # same real client (last hop added by our proxy), different spoofed prefix
            assert c.get("/models", headers=hdr("8.8.8.8, 10.0.0.1")).status_code == 429
            # a different real client
            assert c.get("/models", headers=hdr("9.9.9.9, 10.0.0.2")).status_code == 200

    def test_trust_proxy_without_header_falls_back_to_peer(self):
        with _app(rate_limit_per_minute=1, rate_limit_burst=1, trust_proxy=True) as c:
            assert c.get("/models").status_code == 200
            assert c.get("/models").status_code == 429


class TestSettings:
    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "120")
        monkeypatch.setenv("RATE_LIMIT_BURST", "20")
        monkeypatch.setenv("TRUST_PROXY", "true")
        s = Settings.from_env()
        assert (s.rate_limit_per_minute, s.rate_limit_burst, s.trust_proxy) == (120, 20, True)

    def test_unset_means_disabled(self, monkeypatch):
        for k in ("RATE_LIMIT_PER_MINUTE", "RATE_LIMIT_BURST", "TRUST_PROXY"):
            monkeypatch.delenv(k, raising=False)
        s = Settings.from_env()
        assert (s.rate_limit_per_minute, s.rate_limit_burst, s.trust_proxy) == (None, None, False)

    @pytest.mark.parametrize("bad", ["0", "-5", "abc"])
    def test_invalid_values_fail_fast(self, monkeypatch, bad):
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", bad)
        with pytest.raises(ValueError, match="RATE_LIMIT_PER_MINUTE"):
            Settings.from_env()
