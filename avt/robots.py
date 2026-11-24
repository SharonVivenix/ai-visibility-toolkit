"""Small robots.txt evaluator following the matching rules in RFC 9309.

Longest matching path pattern wins. Allow beats Disallow on a tie.
Supports the * wildcard and the $ end anchor. An empty Disallow allows everything.
"""
from __future__ import annotations

import re
from typing import List, Tuple


class Robots:
    def __init__(self, text: str):
        self.sitemaps: List[str] = []
        self.groups: List[Tuple[List[str], List[Tuple[str, str]]]] = []
        self._parse(text)

    def _parse(self, text: str) -> None:
        agents: List[str] = []
        rules: List[Tuple[str, str]] = []
        in_rules = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (p.strip() for p in line.split(":", 1))
            key = key.lower()
            if key == "sitemap":
                self.sitemaps.append(value)
            elif key == "user-agent":
                if in_rules:
                    self.groups.append((agents, rules))
                    agents, rules, in_rules = [], [], False
                agents.append(value.lower())
            elif key in ("allow", "disallow"):
                in_rules = True
                rules.append((key, value))
        if agents:
            self.groups.append((agents, rules))

    def _rules_for(self, agent: str) -> List[Tuple[str, str]]:
        agent = agent.lower()
        exact = [r for a, r in self.groups if agent in a]
        chosen = exact or [r for a, r in self.groups if "*" in a]
        return [rule for group in chosen for rule in group]

    @staticmethod
    def _to_regex(pattern: str) -> "re.Pattern[str]":
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        rx = ".*".join(re.escape(part) for part in body.split("*"))
        return re.compile("^" + rx + ("$" if anchored else ""))

    def allowed(self, agent: str, path: str = "/") -> bool:
        best_len, verdict = -1, True
        for kind, pattern in self._rules_for(agent):
            if pattern == "":
                continue
            if self._to_regex(pattern).match(path):
                length = len(pattern)
                if length > best_len or (length == best_len and kind == "allow"):
                    best_len, verdict = length, kind == "allow"
        return verdict
