import io
import json
import os

import pytest

from src import cli
from src.cli import EXIT_ERROR, EXIT_OK, EXIT_UNREACHABLE, format_output, main


@pytest.fixture
def run(live_server, capsys):
    """Run `ais ...` against the live server and return (exit_code, stdout, stderr)."""

    def _run(*argv):
        code = main([*argv, "--url", live_server.url] if argv[0] != "serve" else list(argv))
        out = capsys.readouterr()
        return code, out.out, out.err

    return _run


def _json(run, *argv):
    code, out, _ = run(*argv, "--json")
    assert code == EXIT_OK
    return json.loads(out)


class TestFormatOutput:
    def test_text(self):
        assert format_output({"text": "hi"}) == "hi"

    def test_label(self):
        assert format_output({"label": "positive", "score": 0.7311}) == "positive (0.73)"

    def test_short_embedding(self):
        assert format_output({"embedding": [0.5, -0.25]}) == "[0.500, -0.250] (2 dims)"

    def test_long_embedding_is_abbreviated(self):
        out = format_output({"embedding": [0.1] * 20})
        assert out.endswith(", ...] (20 dims)")
        assert out.count("0.100") == 6

    def test_unknown_shape_falls_back_to_json(self):
        assert format_output({"x": 1}) == '{"x": 1}'


class TestModels:
    def test_empty_list_is_helpful(self, run):
        code, out, _ = run("models", "list")
        assert code == EXIT_OK
        assert "ais models create" in out

    def test_create_list_show_delete(self, run):
        code, out, _ = run("models", "create", "sent", "--type", "text-classification")
        assert code == EXIT_OK
        assert "created sent (text-classification)" in out

        _, out, _ = run("models", "list")
        assert "NAME" in out
        assert "sent" in out
        assert "text-classification" in out

        _, out, _ = run("models", "show", "sent")
        assert json.loads(out)["name"] == "sent"

        code, out, _ = run("models", "delete", "sent")
        assert code == EXIT_OK
        assert "deleted sent" in out
        assert run("models", "show", "sent")[0] == EXIT_ERROR

    def test_create_with_config(self, run):
        run("models", "create", "e", "-t", "embedding", "--config", '{"dimensions": 3}')
        _, out, _ = run("infer", "e", "hi", "--json")
        assert len(json.loads(out)["output"]["embedding"]) == 3

    def test_bad_config_json(self, run):
        code, _, err = run("models", "create", "x", "-t", "embedding", "--config", "{nope")
        assert code == EXIT_ERROR
        assert "not valid JSON" in err

    def test_list_json_and_limit_hint(self, run):
        for n in range(3):
            run("models", "create", f"m{n}", "-t", "embedding")
        assert len(_json(run, "models", "list")) == 3
        _, out, _ = run("models", "list", "--limit", "2")
        assert "showing 2 of 3" in out

    def test_duplicate_is_an_error(self, run):
        run("models", "create", "d", "-t", "embedding")
        code, _, err = run("models", "create", "d", "-t", "embedding")
        assert code == EXIT_ERROR
        assert "already exists" in err


class TestInfer:
    def test_classification_is_readable(self, run):
        run("models", "create", "sent", "-t", "text-classification")
        code, out, _ = run("infer", "sent", "not", "bad", "at", "all")
        assert code == EXIT_OK
        assert out.startswith("positive (")

    def test_by_id(self, run):
        mid = _json(run, "models", "create", "g", "-t", "text-generation")["id"]
        _, out, _ = run("infer", mid, "hello")
        assert out.strip() == "Generated response for: hello"

    def test_json_output_is_the_full_inference(self, run):
        run("models", "create", "g", "-t", "text-generation")
        inf = _json(run, "infer", "g", "hello")
        assert inf["status"] == "completed"
        assert inf["input"] == "hello"

    def test_stream(self, run):
        run("models", "create", "g", "-t", "text-generation")
        code, out, _ = run("infer", "g", "hello world", "--stream")
        assert code == EXIT_OK
        assert out == "Generated response for: hello world\n"

    def test_stream_json(self, run):
        run("models", "create", "g", "-t", "text-generation")
        done = _json(run, "infer", "g", "hi", "--stream")
        assert done["output"]["text"] == "Generated response for: hi"

    def test_stream_wrong_type(self, run):
        run("models", "create", "e", "-t", "embedding")
        code, _, err = run("infer", "e", "hi", "--stream")
        assert code == EXIT_ERROR
        assert "only supported for text-generation" in err

    def test_reads_stdin(self, run, monkeypatch):
        run("models", "create", "g", "-t", "text-generation")
        monkeypatch.setattr("sys.stdin", io.StringIO("piped in\n"))
        _, out, _ = run("infer", "g")
        assert out.strip() == "Generated response for: piped in"

    def test_reads_stdin_with_dash(self, run, monkeypatch):
        run("models", "create", "g", "-t", "text-generation")
        monkeypatch.setattr("sys.stdin", io.StringIO("dash"))
        _, out, _ = run("infer", "g", "-")
        assert out.strip() == "Generated response for: dash"

    def test_reads_file(self, run, tmp_path):
        run("models", "create", "g", "-t", "text-generation")
        f = tmp_path / "in.txt"
        f.write_text("from a file\n")
        _, out, _ = run("infer", "g", "-f", str(f))
        assert out.strip() == "Generated response for: from a file"

    def test_empty_stdin_is_an_error(self, run, monkeypatch):
        run("models", "create", "g", "-t", "text-generation")
        monkeypatch.setattr("sys.stdin", io.StringIO("  \n"))
        code, _, err = run("infer", "g")
        assert code == EXIT_ERROR
        assert "no input" in err

    def test_unknown_model(self, run):
        code, _, err = run("infer", "ghost", "hi")
        assert code == EXIT_ERROR
        assert "model not found: ghost" in err


class TestBatchAndHistory:
    def test_batch_args(self, run):
        run("models", "create", "sent", "-t", "text-classification")
        code, out, _ = run("batch", "sent", "great", "terrible", "a table")
        assert code == EXIT_OK
        assert "INPUT" in out
        assert "positive" in out
        assert "negative" in out
        assert "neutral" in out

    def test_batch_file_skips_blank_lines(self, run, tmp_path):
        run("models", "create", "g", "-t", "text-generation")
        f = tmp_path / "in.txt"
        f.write_text("one\n\n  \ntwo\n")
        results = _json(run, "batch", "g", "-f", str(f))
        assert [r["input"] for r in results] == ["one", "two"]

    def test_batch_stdin(self, run, monkeypatch):
        run("models", "create", "g", "-t", "text-generation")
        monkeypatch.setattr("sys.stdin", io.StringIO("a\nb\nc\n"))
        results = _json(run, "batch", "g", "-f", "-")
        assert [r["input"] for r in results] == ["a", "b", "c"]

    def test_batch_with_no_inputs(self, run, monkeypatch):
        run("models", "create", "g", "-t", "text-generation")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        code, _, err = run("batch", "g")
        assert code == EXIT_ERROR
        assert "no inputs" in err

    def test_history(self, run):
        run("models", "create", "g", "-t", "text-generation")
        _, out, _ = run("history", "g")
        assert "no inferences yet" in out
        run("batch", "g", "x", "y", "z")
        _, out, _ = run("history", "g")
        assert "WHEN" in out
        assert "Generated response for: y" in out
        _, out, _ = run("history", "g", "--limit", "1")
        assert "showing 1 of 3" in out
        assert len(_json(run, "history", "g")) == 3


class TestDemoHealthMetrics:
    def test_demo(self, run):
        code, out, _ = run("demo")
        assert code == EXIT_OK
        for expected in ("demo-sentiment", "positive", "negative", "neutral", "dims", "Generated"):
            assert expected in out
        assert "Health: models=3" in out

    def test_demo_is_repeatable(self, run):
        assert run("demo")[0] == EXIT_OK
        assert run("demo")[0] == EXIT_OK
        assert len(_json(run, "models", "list")) == 3  # models are reused, not duplicated

    def test_demo_json(self, run):
        code, out, _ = run("demo", "--json")
        assert code == EXIT_OK
        assert json.loads(out)["models"] == ["demo-sentiment", "demo-embedder", "demo-writer"]

    def test_health(self, run):
        _, out, _ = run("health")
        assert out.startswith("ok  v")
        assert "storage=sqlite" in out
        assert _json(run, "health")["status"] == "ok"

    def test_metrics(self, run):
        _, out, _ = run("metrics")
        assert "# TYPE http_requests_total counter" in out


class TestFailures:
    def test_unreachable_exit_code_and_hint(self, dead_url, capsys):
        code = main(["health", "--url", dead_url])
        err = capsys.readouterr().err
        assert code == EXIT_UNREACHABLE
        assert "cannot reach" in err
        assert "ais serve" in err

    def test_auth_hint(self, secured_server, capsys):
        code = main(["models", "list", "--url", secured_server.url])
        assert code == EXIT_ERROR
        assert "AIS_API_KEY" in capsys.readouterr().err

    def test_api_key_flag_and_env(self, secured_server, capsys, monkeypatch):
        assert main(["models", "list", "--url", secured_server.url, "--api-key", "s3cret"]) == 0
        monkeypatch.setenv("AIS_API_KEY", "s3cret")
        monkeypatch.setenv("AIS_URL", secured_server.url)
        assert main(["models", "list"]) == EXIT_OK  # defaults are read from the environment
        capsys.readouterr()

    def test_missing_command(self):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2

    def test_bad_model_type_rejected_by_parser(self):
        with pytest.raises(SystemExit) as exc:
            main(["models", "create", "x", "--type", "bogus"])
        assert exc.value.code == 2

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        assert capsys.readouterr().out.startswith("ais ")

    def test_missing_file(self, live_server, capsys):
        main(["models", "create", "g", "-t", "text-generation", "--url", live_server.url])
        capsys.readouterr()
        code = main(["infer", "g", "-f", "/no/such/file", "--url", live_server.url])
        assert code == EXIT_ERROR
        assert "error:" in capsys.readouterr().err


class TestServe:
    def test_serve_translates_flags_to_env(self, monkeypatch):
        called = []
        monkeypatch.setattr("src.server.main", lambda: called.append(True))
        for k in ("HOST", "PORT", "DATABASE_PATH", "API_KEY", "LOG_LEVEL"):
            monkeypatch.setenv(k, "")  # registers cleanup so nothing leaks into other tests
            monkeypatch.delenv(k)
        code = main(
            [
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "4567",
                "--db",
                "/tmp/x.db",
                "--api-key",
                "k",
                "--log-level",
                "debug",
            ]
        )
        assert code == EXIT_OK
        assert called == [True]
        assert os.environ["PORT"] == "4567"
        assert os.environ["DATABASE_PATH"] == "/tmp/x.db"
        assert os.environ["API_KEY"] == "k"
        assert os.environ["HOST"] == "127.0.0.1"
        assert os.environ["LOG_LEVEL"] == "debug"

    def test_serve_leaves_unset_flags_alone(self, monkeypatch):
        monkeypatch.setattr("src.server.main", lambda: None)
        monkeypatch.setenv("PORT", "")
        monkeypatch.delenv("PORT")
        main(["serve"])
        assert "PORT" not in os.environ


def test_module_is_importable_as_script():
    assert callable(cli.main)
