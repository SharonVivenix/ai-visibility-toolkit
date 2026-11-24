"""Visibility metrics from stored answers.

Input is JSON Lines. One record per prompt run:
  {"prompt_id": "p1", "engine": "chatgpt", "ts": "2026-11-02", "answer": "...",
   "citations": ["https://example.com/page", ...]}
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import date
from typing import Dict, Iterable, List, Sequence, Tuple
from urllib.parse import urlparse


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """95 percent Wilson score interval for k successes out of n runs."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _pattern(names: Sequence[str]) -> "re.Pattern[str]":
    return re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b", re.I)


def _host(url: str) -> str:
    host = urlparse(url if "//" in url else "//" + url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def cites_domain(citations: Iterable, domain: str) -> bool:
    domain = _host(domain)
    for c in citations:
        url = c.get("url", "") if isinstance(c, dict) else str(c)
        host = _host(url)
        if host == domain or host.endswith("." + domain):
            return True
    return False


def first_mention_order(answer: str, entities: Dict[str, Sequence[str]]) -> List[str]:
    """Entities in the order they first appear in the answer."""
    found = []
    for name, aliases in entities.items():
        m = _pattern(aliases).search(answer)
        if m:
            found.append((m.start(), name))
    return [name for _, name in sorted(found)]


def _bucket(rec: dict, by: str) -> str:
    if by == "engine":
        return rec["engine"]
    if by == "prompt":
        return rec["prompt_id"]
    if by == "week":
        y, w, _ = date.fromisoformat(rec["ts"][:10]).isocalendar()
        return f"{y}-W{w:02d}"
    return "overall"


def score(records: Iterable[dict], brand: str, aliases: Sequence[str], domain: str,
          competitors: Dict[str, Sequence[str]], by: str = "engine") -> Dict[str, dict]:
    entities = {brand: [brand, *aliases], **competitors}
    groups: Dict[str, dict] = defaultdict(lambda: {
        "runs": 0, "mentioned": 0, "cited": 0, "positions": [], "mentions": defaultdict(int)})
    for rec in records:
        g = groups[_bucket(rec, by)]
        order = first_mention_order(rec.get("answer", ""), entities)
        g["runs"] += 1
        for name in order:
            g["mentions"][name] += 1
        if brand in order:
            g["mentioned"] += 1
            g["positions"].append(order.index(brand) + 1)
        if cites_domain(rec.get("citations", []), domain):
            g["cited"] += 1
    result = {}
    for key, g in sorted(groups.items()):
        n = g["runs"]
        total_mentions = sum(g["mentions"].values())
        lo, hi = wilson(g["mentioned"], n)
        result[key] = {
            "runs": n,
            "mention_rate": g["mentioned"] / n,
            "mention_ci95": [round(lo, 3), round(hi, 3)],
            "citation_rate": g["cited"] / n,
            "avg_position": (sum(g["positions"]) / len(g["positions"])) if g["positions"] else None,
            "share_of_voice": (g["mentions"][brand] / total_mentions) if total_mentions else 0.0,
        }
    return result


def load_jsonl(path: str) -> List[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def render(result: Dict[str, dict], by: str) -> str:
    head = f"{by:<14}{'runs':>5}{'mention':>9}{'95% CI':>16}{'cited':>8}{'avg pos':>9}{'SoV':>7}"
    out = [head]
    for key, r in result.items():
        pos = f"{r['avg_position']:.2f}" if r["avg_position"] else "n/a"
        ci = f"{r['mention_ci95'][0]:.2f} to {r['mention_ci95'][1]:.2f}"
        out.append(f"{key:<14}{r['runs']:>5}{r['mention_rate']:>8.0%}{ci:>16}"
                   f"{r['citation_rate']:>8.0%}{pos:>9}{r['share_of_voice']:>7.0%}")
    return "\n".join(out)
