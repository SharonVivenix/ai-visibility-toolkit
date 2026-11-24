"""Page level AI readiness audit. Pure functions plus one fetch helper."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .bots import BOTS, RETRIEVAL_TOKENS
from .robots import Robots

USER_AGENT = "avt/0.1 (ai-visibility-toolkit audit)"
ENTITY_TYPES = {"Organization", "Person", "Product", "Article", "BlogPosting",
                "NewsArticle", "SoftwareApplication", "LocalBusiness", "WebSite"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
ANSWER_MIN_WORDS, ANSWER_MAX_WORDS = 15, 70
TEXT_FULL, TEXT_HALF = 300, 100


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: Optional[str] = None
        self.title = ""
        self.meta: Dict[str, str] = {}
        self.canonical: Optional[str] = None
        self.headings: List[tuple] = []
        self.paragraphs: List[tuple] = []  # (text, after_h1)
        self.jsonld: List[str] = []
        self.text: List[str] = []
        self._skip: Optional[str] = None
        self._ld = False
        self._mode: Optional[str] = None
        self._buf: List[str] = []
        self._seen_h1 = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang") or None
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical = a.get("href")
        elif tag in ("script", "style", "noscript"):
            self._skip = tag
            self._ld = tag == "script" and "ld+json" in a.get("type", "").lower()
            self._buf = []
        elif tag in HEADINGS or tag in ("p", "title"):
            self._mode, self._buf = tag, []

    def handle_data(self, data):
        if self._skip:
            if self._ld:
                self._buf.append(data)
            return
        self.text.append(data)
        if self._mode:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._skip and tag == self._skip:
            if self._ld:
                self.jsonld.append("".join(self._buf))
            self._skip, self._ld, self._buf = None, False, []
        elif self._mode and tag == self._mode:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if tag == "title":
                self.title = text
            elif tag == "p":
                self.paragraphs.append((text, self._seen_h1))
            else:
                self.headings.append((int(tag[1]), text))
                if tag == "h1":
                    self._seen_h1 = True
            self._mode, self._buf = None, []


def _jsonld_types(blobs: List[str]) -> tuple:
    types, dated, parsed = set(), False, 0

    def walk(node):
        nonlocal dated
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            t = node.get("@type")
            for value in (t if isinstance(t, list) else [t]):
                if isinstance(value, str):
                    types.add(value)
            if node.get("dateModified"):
                dated = True
            for value in node.values():
                if isinstance(value, (list, dict)):
                    walk(value)

    for blob in blobs:
        try:
            walk(json.loads(blob))
            parsed += 1
        except ValueError:
            continue
    return types, dated, parsed


@dataclass
class Check:
    id: str
    weight: int
    earned: float  # 0.0 to 1.0
    detail: str
    fix: str = ""


@dataclass
class Report:
    url: str
    checks: List[Check] = field(default_factory=list)
    training_blocked: List[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        total = sum(c.weight for c in self.checks)
        got = sum(c.weight * c.earned for c in self.checks)
        return round(100 * got / total) if total else 0

    def to_dict(self) -> dict:
        return {"url": self.url, "score": self.score,
                "training_blocked": self.training_blocked,
                "checks": [asdict(c) for c in self.checks]}


def audit_html(html: str, url: str, robots: Optional[Robots] = None,
               llms_status: Optional[int] = None,
               sitemap_status: Optional[int] = None) -> Report:
    page = _Page()
    page.feed(html)
    parsed = urlparse(url)
    path = (parsed.path or "/") + (("?" + parsed.query) if parsed.query else "")
    rep = Report(url=url)
    add = rep.checks.append

    add(Check("https", 5, 1.0 if parsed.scheme == "https" else 0.0,
              f"scheme is {parsed.scheme or 'unknown'}", "Serve the page over HTTPS."))

    if robots is None:
        add(Check("robots_retrieval", 20, 0.0, "robots.txt not available",
                  "Publish /robots.txt. A missing file means crawlers apply their own defaults."))
    else:
        blocked = [t for t in RETRIEVAL_TOKENS if not robots.allowed(t, path)]
        ok = len(RETRIEVAL_TOKENS) - len(blocked)
        detail = f"{ok}/{len(RETRIEVAL_TOKENS)} retrieval bots allowed on {path}"
        if blocked:
            detail += ", blocked: " + ", ".join(blocked)
        add(Check("robots_retrieval", 20, ok / len(RETRIEVAL_TOKENS), detail,
                  "Remove Disallow rules that match these tokens, or add explicit Allow groups."))
        rep.training_blocked = [b.token for b in BOTS
                                if b.purpose == "training" and not robots.allowed(b.token, path)]

    has_sitemap = bool(robots and robots.sitemaps) or sitemap_status == 200
    add(Check("sitemap", 5, 1.0 if has_sitemap else 0.0,
              "sitemap declared or reachable" if has_sitemap else "no sitemap found",
              "Add a Sitemap: line to robots.txt."))

    add(Check("llms_txt", 3, 1.0 if llms_status == 200 else 0.0,
              f"/llms.txt returned {llms_status}" if llms_status else "/llms.txt not checked",
              "Optional. llms.txt is a proposal and no major engine has confirmed it reads it."))

    words = len(re.findall(r"\w+", " ".join(page.text)))
    frac = 1.0 if words >= TEXT_FULL else 0.5 if words >= TEXT_HALF else 0.0
    add(Check("server_text", 15, frac, f"{words} words in the server rendered HTML",
              "Render the main content on the server. Several AI crawlers do not run JavaScript."))

    types, dated, n_blobs = _jsonld_types(page.jsonld)
    add(Check("jsonld", 10, 1.0 if n_blobs else 0.0,
              f"{n_blobs} valid JSON-LD block(s)" if n_blobs else "no parseable JSON-LD",
              "Add a JSON-LD block that describes the page."))
    entities = sorted(types & ENTITY_TYPES)
    add(Check("entity_markup", 7, 1.0 if entities else 0.0,
              f"entity types: {', '.join(entities)}" if entities else "no entity type found",
              "Declare who or what the page is about with Organization, Product or Article."))

    has_h1 = any(h[0] == 1 for h in page.headings)
    first = next((t for t, after in page.paragraphs
                  if (after or not has_h1) and len(t.split()) >= 8), "")
    n = len(first.split())
    add(Check("answer_first", 12, 1.0 if ANSWER_MIN_WORDS <= n <= ANSWER_MAX_WORDS else 0.0,
              f"first paragraph is {n} words" if first else "no opening paragraph found",
              f"Open with a direct answer of {ANSWER_MIN_WORDS} to {ANSWER_MAX_WORDS} words."))

    levels = [h[0] for h in page.headings]
    skips = any(b - a > 1 for a, b in zip(levels, levels[1:]))
    good = levels.count(1) == 1 and levels.count(2) >= 2 and not skips
    add(Check("headings", 8, 1.0 if good else 0.0,
              f"h1 x{levels.count(1)}, h2 x{levels.count(2)}, skipped levels: {skips}",
              "Use one h1, at least two h2 sections and no skipped levels."))

    desc = page.meta.get("description", "")
    add(Check("title_meta", 5, 1.0 if page.title and len(desc) >= 50 else 0.0,
              f"title {len(page.title)} chars, description {len(desc)} chars",
              "Write a title and a meta description of at least 50 characters."))
    add(Check("canonical", 5, 1.0 if page.canonical else 0.0,
              page.canonical or "no canonical link", 'Add <link rel="canonical">.'))

    modified = dated or any(k in page.meta for k in ("article:modified_time", "og:updated_time"))
    add(Check("freshness", 5, 1.0 if modified else 0.0,
              "modified date present" if modified else "no modified date",
              "Expose dateModified in JSON-LD or article:modified_time."))
    return rep


def _fetch(url: str, limit: int = 2_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read(limit).decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, ""
    except (urllib.error.URLError, TimeoutError):
        return 0, ""


def audit_url(url: str) -> Report:
    parsed = urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    status, html = _fetch(url)
    if status != 200:
        raise RuntimeError(f"GET {url} returned {status}")
    r_status, r_text = _fetch(root + "/robots.txt")
    l_status, _ = _fetch(root + "/llms.txt")
    s_status, _ = _fetch(root + "/sitemap.xml")
    robots = Robots(r_text) if r_status == 200 else None
    return audit_html(html, url, robots, l_status, s_status)
