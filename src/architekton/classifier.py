"""Heuristic prompt complexity scorer. No LLM calls, no network."""

import math
import re

BASE_SCORE = 0.5
SIGNAL_WEIGHT = 0.12
LONG_PROMPT_TOKENS = 400
SHORT_PROMPT_TOKENS = 80
LENGTH_WEIGHT = 0.15
MAX_LENGTH_BONUS = 0.30
# Pasted logs and file contents are full of words like "list" and "format".
# Only the opening of the prompt says what the user is asking for.
SCAN_CHARS = 800

HEAVY_PATTERNS = [
    r"\barchitect\w*", r"\bdesign\w*", r"\brefactor\w*", r"\brestructur\w*",
    r"\breview\w*", r"\baudit\w*", r"\bdebug\w*", r"\binvestigat\w*",
    r"\broot cause\b", r"\ball files\b", r"\bacross the codebase\b",
    r"\bmulti-file\b", r"\bsecurity\b", r"\bexploit\w*",
]
LIGHT_PATTERNS = [
    r"\brename\w*", r"\btypo\w*", r"\bfix spelling\b", r"\badd comment\w*",
    r"\bformat(?:ting|ted)?\b", r"\bwhat is\b", r"\bshow me\b", r"\blist\b",
    r"\bgit status\b", r"\brun tests\b", r"\bsingle file\b", r"\bone line\b",
    r"\bcommit message\b",
]
HEAVY_REGEXES = [re.compile(pattern, re.IGNORECASE) for pattern in HEAVY_PATTERNS]
LIGHT_REGEXES = [re.compile(pattern, re.IGNORECASE) for pattern in LIGHT_PATTERNS]


def estimate_tokens(text):
    return math.ceil(len(text) / 4)


def count_hits(regexes, text):
    """Count distinct patterns that match, so repeating a word adds nothing."""
    return sum(1 for regex in regexes if regex.search(text))


def score(text):
    tokens = estimate_tokens(text)
    total = BASE_SCORE
    head = text[:SCAN_CHARS]
    heavy_hits = count_hits(HEAVY_REGEXES, head)
    light_hits = count_hits(LIGHT_REGEXES, head)
    if tokens > LONG_PROMPT_TOKENS:
        total += min(LENGTH_WEIGHT * math.log2(tokens / LONG_PROMPT_TOKENS), MAX_LENGTH_BONUS)
    elif tokens < SHORT_PROMPT_TOKENS and heavy_hits == 0:
        # Short-prompt penalty only applies when there are no heavy signals.
        # A concise architecture question is still opus work.
        total -= LENGTH_WEIGHT
    total += SIGNAL_WEIGHT * heavy_hits
    total -= SIGNAL_WEIGHT * light_hits
    return round(min(max(total, 0.0), 1.0), 2)


def tier_for_score(value, thresholds):
    if value >= thresholds["heavy"]:
        return "opus"
    if value <= thresholds["light"]:
        return "haiku"
    return "sonnet"


def classify(text, config):
    value = score(text)
    tier = tier_for_score(value, config["thresholds"])
    return {"score": value, "tier": tier, "recommended_model": config["models"][tier]}


def get_tier_of_model(model):
    """Map a model alias or full ID to opus/sonnet/haiku, or None if unknown."""
    lowered = (model or "").lower()
    for tier in ("opus", "sonnet", "haiku"):
        if tier in lowered:
            return tier
    return None
