import json

import pytest

from src.bench import SCENARIOS, Result, Scenario, run_benchmark, run_scenario
from src.cli import EXIT_ERROR, EXIT_OK, main
from src.client import Client


class TestResult:
    def test_percentiles(self):
        r = Result("x", requests=100, seconds=2.0, latencies_ms=[float(i) for i in range(1, 101)])
        assert r.rps == 50.0
        assert r.percentile(50) == 51.0
        assert r.percentile(99) == 100.0

    def test_empty_result_does_not_divide_by_zero(self):
        r = Result("x")
        assert (r.rps, r.percentile(50)) == (0.0, 0.0)

    def test_as_dict_rounds(self):
        d = Result("x", requests=3, seconds=1.0, latencies_ms=[1.23456]).as_dict()
        assert d == {
            "scenario": "x",
            "requests": 3,
            "errors": 0,
            "rps": 3.0,
            "p50_ms": 1.23,
            "p95_ms": 1.23,
            "p99_ms": 1.23,
        }


class TestRunBenchmark:
    def test_runs_every_scenario_without_errors(self, live_server):
        seen = []
        results = run_benchmark(
            Client(live_server.url), duration=0.15, concurrency=2, progress=seen.append
        )
        assert [r.name for r in results] == [s.name for s in SCENARIOS] == seen
        for r in results:
            assert r.requests > 0, r.name
            assert r.errors == 0, r.name
            assert r.rps > 0
            assert r.percentile(50) <= r.percentile(99)

    def test_cleans_up_its_models(self, live_server):
        client = Client(live_server.url)
        run_benchmark(client, duration=0.1, concurrency=1, scenarios=SCENARIOS[:1])
        assert client.list_models() == []

    def test_replaces_stale_models_from_an_earlier_run(self, live_server):
        client = Client(live_server.url)
        client.create_model("bench-generation", "text-generation")
        results = run_benchmark(client, duration=0.1, concurrency=1, scenarios=SCENARIOS[2:3])
        assert results[0].errors == 0

    def test_unexpected_statuses_are_counted_as_errors(self, live_server):
        teapot = Scenario("expects 418", "GET", lambda m: "/health", expect=(418,))
        [result] = run_benchmark(
            Client(live_server.url), duration=0.15, concurrency=2, scenarios=[teapot]
        )
        assert result.requests > 0
        assert result.errors == result.requests

    def test_connection_failures_are_errors_not_crashes(self, live_server, dead_url):
        probe = Scenario("probe", "GET", lambda m: "/health")
        result = run_scenario(dead_url, None, probe, {}, duration=0.2, concurrency=2)
        assert result.requests > 0
        assert result.errors == result.requests

    def test_api_key_is_sent(self, secured_server):
        results = run_benchmark(
            Client(secured_server.url, api_key="s3cret"),
            duration=0.1,
            concurrency=1,
            scenarios=SCENARIOS[:2],
        )
        assert all(r.errors == 0 for r in results)


class TestCli:
    def test_table_output(self, live_server, capsys):
        code = main(["bench", "--url", live_server.url, "--duration", "0.1", "-c", "2"])
        out = capsys.readouterr()
        assert code == EXIT_OK
        assert "REQ/S" in out.out
        assert "infer: embedding (64 dims)" in out.out
        assert "Benchmarking" in out.err  # progress goes to stderr, results to stdout

    def test_json_output(self, live_server, capsys):
        code = main(["bench", "--url", live_server.url, "--duration", "0.1", "-c", "1", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert code == EXIT_OK
        assert len(data) == len(SCENARIOS)
        assert {"scenario", "rps", "p50_ms", "p95_ms", "p99_ms", "errors"} <= data[0].keys()

    def test_nonzero_exit_when_requests_fail(self, secured_server, capsys):
        code = main(["bench", "--url", secured_server.url, "--duration", "0.1", "-c", "1"])
        assert code == EXIT_ERROR  # setup fails with 401, reported as an error
        assert "error:" in capsys.readouterr().err

    @pytest.mark.parametrize("flag", ["--duration", "--concurrency"])
    def test_flags_require_numbers(self, flag):
        with pytest.raises(SystemExit):
            main(["bench", flag, "abc"])
