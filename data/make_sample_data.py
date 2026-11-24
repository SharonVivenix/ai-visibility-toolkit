"""Generate the synthetic sample files in this folder. Deterministic, fictional brands.

    python data/make_sample_data.py
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
rng = random.Random(11)

# ---- access log ---------------------------------------------------------
UAS = [
    ("Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Safari/537.36", 60),
    ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", 14),
    ("Mozilla/5.0 AppleWebKit/537.36 (compatible; GPTBot/1.1; +https://openai.com/gptbot)", 5),
    ("Mozilla/5.0 AppleWebKit/537.36 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)", 6),
    ("Mozilla/5.0 AppleWebKit/537.36 (compatible; ChatGPT-User/1.0; +https://openai.com/bot)", 4),
    ("Mozilla/5.0 AppleWebKit/537.36 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", 5),
    ("Mozilla/5.0 AppleWebKit/537.36 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)", 4),
    ("Mozilla/5.0 (compatible; CCBot/2.0; +https://commoncrawl.org/faq/)", 2),
    ("Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)", 3),
]
PATHS = ["/", "/pricing", "/blog/what-is-aeo", "/blog/geo-checklist", "/docs/api",
         "/blog/schema-guide", "/robots.txt", "/llms.txt", "/sitemap.xml", "/private/reports"]
STATUS = [200] * 17 + [301, 404, 403]

lines = []
for i in range(420):
    ua = rng.choices([u for u, _ in UAS], [w for _, w in UAS])[0]
    path = rng.choice(PATHS)
    status = rng.choice(STATUS)
    if "Bytespider" in ua or "CCBot" in ua:
        status = rng.choice([200, 403, 403])
    ip = f"203.0.113.{rng.randint(1, 250)}"
    ts = f"{1 + i // 20:02d}/Nov/2026:{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d} +0000"
    lines.append(f'{ip} - - [{ts}] "GET {path} HTTP/1.1" {status} {rng.randint(300, 52000)} "-" "{ua}"')
with open(os.path.join(HERE, "sample_access.log"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")

# ---- answers ------------------------------------------------------------
BRAND, RIVALS = "Lumen Notes", ["Quillpad", "Notebase"]
ENGINES = {"chatgpt": 0.55, "perplexity": 0.70, "gemini": 0.40, "claude": 0.48}
PROMPTS = [f"p{i:02d}" for i in range(1, 13)]
WEEKS = ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]

records = []
for w_idx, ts in enumerate(WEEKS):
    for engine, base in ENGINES.items():
        for pid in PROMPTS:
            p_brand = min(0.95, base + 0.04 * w_idx)
            names = []
            if rng.random() < p_brand:
                names.append(BRAND)
            for r in RIVALS:
                if rng.random() < 0.6:
                    names.append(r)
            rng.shuffle(names)
            answer = ("Popular options include " + ", then ".join(names) + ".") if names \
                else "It depends on your workflow and team size."
            cites = []
            if BRAND in names and rng.random() < 0.55:
                cites.append("https://www.lumennotes.example/blog/what-is-aeo")
            if rng.random() < 0.5:
                cites.append("https://quillpad.example/compare")
            records.append({"prompt_id": pid, "engine": engine, "ts": ts,
                            "answer": answer, "citations": cites})
with open(os.path.join(HERE, "responses.sample.jsonl"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(json.dumps(r) for r in records) + "\n")
print(len(lines), "log lines,", len(records), "answer records")
