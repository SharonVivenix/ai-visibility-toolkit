"""Registry of AI related crawlers and robots.txt control tokens.

Purpose values:
  training  collects content for model training
  search    builds or queries an index that answer engines cite from
  user      fetches a page live because a person asked a question about it
  mixed     operator documents more than one use
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bot:
    token: str
    operator: str
    purpose: str
    log_visible: bool = True  # False for control tokens that never send requests


BOTS = (
    Bot("GPTBot", "OpenAI", "training"),
    Bot("OAI-SearchBot", "OpenAI", "search"),
    Bot("ChatGPT-User", "OpenAI", "user"),
    Bot("ClaudeBot", "Anthropic", "training"),
    Bot("Claude-SearchBot", "Anthropic", "search"),
    Bot("Claude-User", "Anthropic", "user"),
    Bot("PerplexityBot", "Perplexity", "search"),
    Bot("Perplexity-User", "Perplexity", "user"),
    Bot("Google-Extended", "Google", "training", log_visible=False),
    Bot("Applebot-Extended", "Apple", "training", log_visible=False),
    Bot("CCBot", "Common Crawl", "training"),
    Bot("Bytespider", "ByteDance", "training"),
    Bot("Amazonbot", "Amazon", "mixed"),
    Bot("meta-externalagent", "Meta", "training"),
)

# Bots that decide whether an answer engine can read your page at question time.
RETRIEVAL_TOKENS = (
    "OAI-SearchBot",
    "ChatGPT-User",
    "Claude-SearchBot",
    "Claude-User",
    "PerplexityBot",
    "Perplexity-User",
)

BY_TOKEN = {b.token.lower(): b for b in BOTS}


def classify_user_agent(user_agent: str):
    """Return the Bot whose token appears in the user agent string, or None."""
    ua = user_agent.lower()
    for bot in BOTS:
        if bot.log_visible and bot.token.lower() in ua:
            return bot
    return None
