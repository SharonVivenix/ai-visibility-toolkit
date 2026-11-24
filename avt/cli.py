from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .audit import audit_html, audit_url
from .fanout import to_jsonl
from .logs import analyze, render as render_logs
from .robots import Robots
from .score import load_jsonl, render as render_score, score


def _cmd_audit(a) -> int:
    if a.html:
        html = open(a.html, encoding="utf-8").read()
        robots = Robots(open(a.robots, encoding="utf-8").read()) if a.robots else None
        rep = audit_html(html, a.target, robots)
    else:
        rep = audit_url(a.target)
    if a.json:
        print(json.dumps(rep.to_dict(), indent=2))
    else:
        print(f"AI readiness score: {rep.score}/100  {rep.url}\n")
        for c in rep.checks:
            mark = "PASS" if c.earned == 1 else "PART" if c.earned > 0 else "FAIL"
            print(f"[{mark}] {c.id:<17}{c.weight:>3} pts  {c.detail}")
            if c.earned < 1 and c.fix:
                print(f"       fix: {c.fix}")
        if rep.training_blocked:
            print(f"\ntraining bots blocked (not scored): {', '.join(rep.training_blocked)}")
    return 0 if rep.score >= a.fail_under else 1


def _cmd_logs(a) -> int:
    with open(a.logfile, encoding="utf-8", errors="replace") as fh:
        stats = analyze(fh)
    if a.json:
        meta = stats.pop("_meta")
        out = {k: {**v, "paths": dict(v["paths"])} for k, v in stats.items()}
        print(json.dumps({"meta": meta, "bots": out}, indent=2))
    else:
        print(render_logs(stats))
    return 0


def _cmd_score(a) -> int:
    rivals = {}
    for item in a.competitor or []:
        name, _, rest = item.partition("=")
        rivals[name] = [name, *[x for x in rest.split(",") if x]]
    res = score(load_jsonl(a.responses), a.brand, a.alias or [], a.domain, rivals, a.by)
    print(json.dumps(res, indent=2) if a.json else render_score(res, a.by))
    return 0


def _cmd_fanout(a) -> int:
    with open(a.config, encoding="utf-8") as fh:
        print(to_jsonl(json.load(fh), a.brand))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="avt", description="AI visibility toolkit")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("audit", help="score a page for AI readiness")
    s.add_argument("target", help="page URL")
    s.add_argument("--html", help="read HTML from a file instead of fetching")
    s.add_argument("--robots", help="robots.txt file to use with --html")
    s.add_argument("--json", action="store_true")
    s.add_argument("--fail-under", type=int, default=0, help="exit 1 below this score")
    s.set_defaults(fn=_cmd_audit)

    s = sub.add_parser("logs", help="count AI crawler hits in an access log")
    s.add_argument("logfile")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_logs)

    s = sub.add_parser("score", help="mention, citation and share of voice metrics")
    s.add_argument("responses", help="JSONL file of answers")
    s.add_argument("--brand", required=True)
    s.add_argument("--alias", action="append", help="extra brand spelling, repeatable")
    s.add_argument("--domain", required=True)
    s.add_argument("--competitor", action="append", help="Name or Name=alias1,alias2")
    s.add_argument("--by", choices=["engine", "prompt", "week", "overall"], default="engine")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_score)

    s = sub.add_parser("fanout", help="expand prompt templates from a JSON config")
    s.add_argument("config")
    s.add_argument("--brand", default="")
    s.set_defaults(fn=_cmd_fanout)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (OSError, RuntimeError, ValueError, KeyError) as err:
        print(f"avt: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
