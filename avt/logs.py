"""Count AI crawler hits in combined format access logs."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, Iterable

from .bots import classify_user_agent

LINE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+)[^"]*" '
    r'(?P<status>\d{3}) \S+ "[^"]*" "(?P<ua>[^"]*)"')


def analyze(lines: Iterable[str]) -> Dict[str, dict]:
    stats: Dict[str, dict] = defaultdict(
        lambda: {"hits": 0, "ok": 0, "paths": Counter(), "operator": "", "purpose": ""})
    total = unparsed = 0
    for line in lines:
        m = LINE.match(line)
        if not m:
            unparsed += 1
            continue
        total += 1
        bot = classify_user_agent(m["ua"])
        if bot is None:
            continue
        s = stats[bot.token]
        s["hits"] += 1
        s["ok"] += m["status"].startswith("2")
        s["paths"][m["path"]] += 1
        s["operator"], s["purpose"] = bot.operator, bot.purpose
    stats["_meta"] = {"requests": total, "unparsed": unparsed}
    return stats


def render(stats: Dict[str, dict], top: int = 3) -> str:
    meta = stats.pop("_meta")
    rows = sorted(stats.items(), key=lambda kv: -kv[1]["hits"])
    out = [f"{meta['requests']} requests parsed, {meta['unparsed']} lines skipped", ""]
    out.append(f"{'bot':<18}{'operator':<14}{'purpose':<10}{'hits':>6}{'2xx':>7}  top paths")
    for token, s in rows:
        pct = 100 * s["ok"] / s["hits"]
        paths = ", ".join(p for p, _ in s["paths"].most_common(top))
        out.append(f"{token:<18}{s['operator']:<14}{s['purpose']:<10}{s['hits']:>6}{pct:>6.0f}%  {paths}")
    if not rows:
        out.append("no AI crawler traffic found")
    return "\n".join(out)
