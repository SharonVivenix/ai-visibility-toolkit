"""Expand prompt templates into a tracking set (query fan out for your own prompts)."""
from __future__ import annotations

import hashlib
import json
from string import Formatter
from typing import Iterator


def _fields(template: str) -> set:
    return {f for _, f, _, _ in Formatter().parse(template) if f}


def expand(config: dict, brand: str = "") -> Iterator[dict]:
    seen = set()
    base = {"category": config["category"], "brand": brand}
    for intent, templates in config["intents"].items():
        for template in templates:
            needs = _fields(template)
            personas = config.get("personas", [""]) if "persona" in needs else [""]
            rivals = config.get("competitors", [""]) if "competitor" in needs else [""]
            for persona in personas:
                for rival in rivals:
                    prompt = template.format_map({**base, "persona": persona, "competitor": rival})
                    if prompt in seen:
                        continue
                    seen.add(prompt)
                    pid = hashlib.sha1(prompt.encode()).hexdigest()[:8]
                    yield {"id": pid, "intent": intent, "prompt": prompt}


def to_jsonl(config: dict, brand: str = "") -> str:
    return "\n".join(json.dumps(row) for row in expand(config, brand))
