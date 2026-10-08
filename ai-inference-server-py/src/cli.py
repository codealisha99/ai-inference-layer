"""``ais``: command-line interface for the AI Inference Server.

    ais serve --db ./data/ai.db          start the server (SQLite-backed)
    ais demo                             create sample models and run them
    ais models create sentiment --type text-classification
    ais infer sentiment "this is not bad at all"
    ais infer writer "tell me a story" --stream
    ais batch sentiment -f reviews.txt
    ais history sentiment

Models can be referenced by name or by id. Use ``--json`` on any command for raw JSON.
Connection settings come from ``--url``/``--api-key`` or ``AIS_URL``/``AIS_API_KEY``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .client import DEFAULT_URL, ApiError, Client, ServerUnreachable
from .engines import MODEL_TYPES

EXIT_OK, EXIT_ERROR, EXIT_UNREACHABLE = 0, 1, 2


# ---- formatting ----------------------------------------------------------------------


def _clip(text: Any, width: int = 48) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= width else s[: width - 1] + "…"


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    cells = [[_clip(c) for c in row] for row in rows]
    widths = [
        max(len(h), *(len(r[i]) for r in cells)) if cells else len(h) for i, h in enumerate(headers)
    ]

    def line(row: Sequence[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)).rstrip()

    return "\n".join([line(headers), line(["-" * w for w in widths]), *(line(r) for r in cells)])


def _when(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def format_output(output: dict[str, Any]) -> str:
    """One-line, human-friendly rendering of an engine output."""
    if "text" in output:
        return str(output["text"])
    if "label" in output:
        return f"{output['label']} ({output['score']:.2f})"
    if "embedding" in output:
        vec = output["embedding"]
        head = ", ".join(f"{v:.3f}" for v in vec[:6])
        return f"[{head}{', ...' if len(vec) > 6 else ''}] ({len(vec)} dims)"
    return json.dumps(output)


def _emit(args: argparse.Namespace, data: Any, human: Callable[[], str]) -> None:
    print(json.dumps(data, indent=2) if args.json else human())


# ---- helpers -------------------------------------------------------------------------


def _read_texts(args: argparse.Namespace, *, allow_lines: bool) -> list[str]:
    """Collect input from arguments, ``-f FILE`` or stdin (``-`` / piped)."""
    source = getattr(args, "file", None)
    if source == "-" or (not source and (args.text == ["-"] or (not args.text and _piped()))):
        raw = sys.stdin.read()
    elif source:
        raw = Path(source).read_text(encoding="utf-8")
    else:
        return list(args.text) if allow_lines else [" ".join(args.text)]
    if allow_lines:
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return [raw.strip()] if raw.strip() else []


def _piped() -> bool:
    try:
        return not sys.stdin.isatty()
    except (ValueError, AttributeError):
        return False


# ---- commands ------------------------------------------------------------------------


def cmd_health(c: Client, args: argparse.Namespace) -> int:
    h = c.health()
    _emit(
        args,
        h,
        lambda: (
            f"ok  v{h['version']}  storage={h.get('storage', '?')}  "
            f"models={h['models']}  inferences={h['inferences']}  up {h['uptimeSeconds']:.0f}s"
        ),
    )
    return EXIT_OK


def cmd_metrics(c: Client, _args: argparse.Namespace) -> int:
    print(c.metrics(), end="")
    return EXIT_OK


def cmd_models_list(c: Client, args: argparse.Namespace) -> int:
    page = c.list_models(limit=args.limit)
    if args.json:
        print(json.dumps(list(page), indent=2))
    elif not page:
        print("no models yet; create one with: ais models create NAME --type TYPE")
    else:
        print(
            _table(
                ["ID", "NAME", "TYPE", "CONFIG", "CREATED"],
                [
                    [
                        m["id"][:8],
                        m["name"],
                        m["type"],
                        json.dumps(m["config"]) if m["config"] else "",
                        _when(m["createdAt"]),
                    ]
                    for m in page
                ],
            )
        )
        if page.total > len(page):
            print(f"\nshowing {len(page)} of {page.total}")
    return EXIT_OK


def cmd_models_create(c: Client, args: argparse.Namespace) -> int:
    config = None
    if args.config:
        try:
            config = json.loads(args.config)
        except json.JSONDecodeError as exc:
            print(f"error: --config is not valid JSON: {exc}", file=sys.stderr)
            return EXIT_ERROR
    m = c.create_model(args.name, args.type, config)
    _emit(args, m, lambda: f"created {m['name']} ({m['type']})  id={m['id']}")
    return EXIT_OK


def cmd_models_show(c: Client, args: argparse.Namespace) -> int:
    m = c.find_model(args.model)
    _emit(args, m, lambda: json.dumps(m, indent=2))
    return EXIT_OK


def cmd_models_delete(c: Client, args: argparse.Namespace) -> int:
    m = c.find_model(args.model)
    c.delete_model(m["id"])
    _emit(args, {"id": m["id"], "removed": True}, lambda: f"deleted {m['name']}")
    return EXIT_OK


def cmd_infer(c: Client, args: argparse.Namespace) -> int:
    texts = _read_texts(args, allow_lines=False)
    if not texts:
        print("error: no input text (pass it as arguments or on stdin)", file=sys.stderr)
        return EXIT_ERROR
    m = c.find_model(args.model)
    if args.stream:
        done: dict[str, Any] | None = None
        for event, data in c.stream(m["id"], texts[0]):
            if event == "token":
                if not args.json:
                    print(data["token"], end="", flush=True)
            elif event == "done":
                done = data
        if args.json:
            print(json.dumps(done, indent=2))
        else:
            print()
        return EXIT_OK
    inf = c.infer(m["id"], texts[0])
    _emit(args, inf, lambda: format_output(inf["output"]))
    return EXIT_OK


def cmd_batch(c: Client, args: argparse.Namespace) -> int:
    texts = _read_texts(args, allow_lines=True)
    if not texts:
        print("error: no inputs (pass texts, -f FILE, or lines on stdin)", file=sys.stderr)
        return EXIT_ERROR
    m = c.find_model(args.model)
    results = c.batch(m["id"], texts)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(
            _table(["INPUT", "RESULT"], [[r["input"], format_output(r["output"])] for r in results])
        )
    return EXIT_OK


def cmd_history(c: Client, args: argparse.Namespace) -> int:
    m = c.find_model(args.model)
    page = c.list_inferences(m["id"], limit=args.limit)
    if args.json:
        print(json.dumps(list(page), indent=2))
    elif not page:
        print(f"no inferences yet for {m['name']}")
    else:
        print(
            _table(
                ["WHEN", "INPUT", "RESULT"],
                [[_when(i["createdAt"]), i["input"], format_output(i["output"])] for i in page],
            )
        )
        if page.total > len(page):
            print(f"\nshowing {len(page)} of {page.total}")
    return EXIT_OK


_DEMO_MODELS = [
    ("demo-sentiment", "text-classification", None),
    ("demo-embedder", "embedding", {"dimensions": 8}),
    ("demo-writer", "text-generation", None),
]


def cmd_demo(c: Client, args: argparse.Namespace) -> int:
    say = (lambda *_a, **_k: None) if args.json else print

    def ensure(name: str, typ: str, config: dict[str, Any] | None) -> dict[str, Any]:
        try:
            return c.find_model(name)
        except ApiError as exc:
            if exc.status != 404:
                raise
            return c.create_model(name, typ, config)

    models = {name: ensure(name, typ, cfg) for name, typ, cfg in _DEMO_MODELS}
    say(f"Server {c.base_url}: " + ", ".join(models) + " ready.\n")

    say("1. Classify sentiment (note the negation handling)")
    for text in [
        "I love this, it is great",
        "not bad at all",
        "this is terrible",
        "a wooden table",
    ]:
        out = c.infer(models["demo-sentiment"]["id"], text)["output"]
        say(f"   {text!r:32} -> {format_output(out)}")

    say("\n2. Batch: embed three sentences in one request")
    emb = c.batch(models["demo-embedder"]["id"], ["hello world", "hello there", "goodbye"])
    for r in emb:
        say(f"   {r['input']!r:16} -> {format_output(r['output'])}")

    say("\n3. Stream generated text token by token")
    say("   ", end="")
    for tok in c.stream_text(models["demo-writer"]["id"], "Inference servers are fun"):
        if not args.json:
            print(tok, end="", flush=True)
    say("\n")

    h = c.health()
    say(f"Health: models={h['models']} inferences={h['inferences']} storage={h['storage']}")
    say(
        "Next: ais history demo-sentiment   |   ais models list   |   open "
        f"{c.base_url}/ in a browser"
    )
    if args.json:
        print(json.dumps({"models": list(models), "health": h}, indent=2))
    return EXIT_OK


def cmd_serve(args: argparse.Namespace) -> int:
    for env, value in (
        ("HOST", args.host),
        ("PORT", args.port),
        ("DATABASE_PATH", args.db),
        ("API_KEY", args.serve_api_key),
        ("LOG_LEVEL", args.log_level),
    ):
        if value is not None:
            os.environ[env] = str(value)
    from .server import main as run_server

    run_server()
    return EXIT_OK


# ---- argument parsing ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="print raw JSON")
    common.add_argument(
        "--url",
        default=os.getenv("AIS_URL", DEFAULT_URL),
        help=f"server URL (default {DEFAULT_URL})",
    )
    common.add_argument(
        "--api-key", default=os.getenv("AIS_API_KEY"), help="API key (or AIS_API_KEY)"
    )

    p = argparse.ArgumentParser(
        prog="ais",
        description="Command-line client and launcher for the AI Inference Server.",
        epilog="Models can be referenced by name or id. Run `ais COMMAND -h` for details.",
    )
    p.add_argument("--version", action="version", version=f"ais {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND", required=True)

    s = sub.add_parser("serve", help="start the server")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.add_argument("--db", metavar="PATH", help="persist to this SQLite file (default: in memory)")
    s.add_argument(
        "--api-key", dest="serve_api_key", metavar="KEY", help="require this API key from clients"
    )
    s.add_argument("--log-level", choices=["debug", "info", "warning", "error"])
    s.set_defaults(func=cmd_serve, local=True)

    sub.add_parser("health", parents=[common], help="server status").set_defaults(func=cmd_health)
    sub.add_parser("metrics", parents=[common], help="Prometheus metrics").set_defaults(
        func=cmd_metrics
    )
    sub.add_parser("demo", parents=[common], help="create sample models and run them").set_defaults(
        func=cmd_demo
    )

    m = sub.add_parser("models", help="manage models").add_subparsers(
        dest="sub", metavar="ACTION", required=True
    )
    ml = m.add_parser("list", parents=[common], help="list models")
    ml.add_argument("--limit", type=int)
    ml.set_defaults(func=cmd_models_list)
    mc = m.add_parser("create", parents=[common], help="create a model")
    mc.add_argument("name")
    mc.add_argument("--type", "-t", required=True, choices=MODEL_TYPES)
    mc.add_argument("--config", "-c", metavar="JSON", help="e.g. '{\"dimensions\": 64}'")
    mc.set_defaults(func=cmd_models_create)
    for name, fn, hlp in (
        ("show", cmd_models_show, "show a model"),
        ("delete", cmd_models_delete, "delete a model and its history"),
    ):
        x = m.add_parser(name, parents=[common], help=hlp)
        x.add_argument("model", metavar="MODEL")
        x.set_defaults(func=fn)

    i = sub.add_parser("infer", parents=[common], help="run one input through a model")
    i.add_argument("model", metavar="MODEL")
    i.add_argument("text", nargs="*", help="input text; omit or use - to read stdin")
    i.add_argument("-f", "--file", help="read the input from a file (- for stdin)")
    i.add_argument("--stream", action="store_true", help="stream tokens (text-generation only)")
    i.set_defaults(func=cmd_infer)

    b = sub.add_parser("batch", parents=[common], help="run many inputs in one request")
    b.add_argument("model", metavar="MODEL")
    b.add_argument("text", nargs="*", help="inputs; omit to read lines from stdin")
    b.add_argument("-f", "--file", help="file with one input per line (- for stdin)")
    b.set_defaults(func=cmd_batch)

    h = sub.add_parser("history", parents=[common], help="show a model's inference history")
    h.add_argument("model", metavar="MODEL")
    h.add_argument("--limit", type=int)
    h.set_defaults(func=cmd_history)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "local", False):
        return int(args.func(args))
    client = Client(args.url, args.api_key)
    try:
        return int(args.func(client, args))
    except ApiError as exc:
        print(
            f"error: {exc.message}"
            + (" (set --api-key or AIS_API_KEY)" if exc.status == 401 else ""),
            file=sys.stderr,
        )
        return EXIT_ERROR
    except ServerUnreachable as exc:
        print(f"error: {exc}\nstart a server with: ais serve", file=sys.stderr)
        return EXIT_UNREACHABLE
    except (BrokenPipeError, KeyboardInterrupt):
        return EXIT_ERROR
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
