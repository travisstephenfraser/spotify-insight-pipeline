"""The label vocabulary and the rules a record must meet before it counts as completed.

`validate` enforces what the supplied checker enforces on a completed record, so a record
that passes here is never the reason the checker says `invalid_schema` or `unsupported_quote`.
"""

import math

TOPICS = (
    "access",
    "usability",
    "playback",
    "downloads",
    "catalog",
    "billing",
    "support",
    "other",
)
# The contract's definition of each topic, word for word.
TOPIC_DEFINITIONS = {
    "access": "Login, signup, password or account access",
    "usability": "Navigation, controls, layout, queue/playlist management, ad interruptions",
    "playback": "Playback failure, crashes, lag, connection failures, audio quality, resource use",
    "downloads": "Downloading, saved music, offline listening, disappearing downloads",
    "catalog": "Missing songs/artists, search/discovery, recommendations, lyrics availability",
    "billing": "Price, charges, subscriptions, paywalls, premium entitlement; explicitly premium-only controls go here",
    "support": "Contacting support and the support response",
    "other": "General praise/criticism, unrelated content, or no supported specific topic",
}
# The contract's precedence order: take the first one that fits.
INTENTS = ("cancellation", "complaint", "request", "praise", "unclear")
# Jev is asked for a named severity, never a digit.
SEVERITY = {
    "no_problem": 1,
    "annoyance": 2,
    "degraded": 3,
    "blocked": 4,
    "serious_harm": 5,
}

# The contract's severity 1: "No reported problem: praise, neutral/unclear content, or a pure feature request".
NO_PROBLEM = ("unclear", "praise", "request")


class InvalidAnswer(Exception):
    """A model answer that cannot become a valid record. The message names the reason."""


def sentiment_from_tone(score):
    """Jev's tone score, a real number from 0 to 4, onto -1 to 1. Out of range is invalid, never clamped."""
    if (
        type(score) not in (int, float)
        or not math.isfinite(score)
        or not 0 <= score <= 4
    ):
        raise InvalidAnswer(f"tone score is not a number from 0 to 4: {score!r}")
    return score / 2 - 1


def validate(text, record):
    """Raise InvalidAnswer unless `record` is a valid completed label for `text`."""

    def bad(reason):
        raise InvalidAnswer(reason)

    if record.get("topic") not in TOPICS:
        bad("topic is not one of the allowed labels")
    if record.get("intent") not in INTENTS:
        bad("intent is not one of the allowed labels")
    severity = record.get("severity")
    if type(severity) is not int or not 1 <= severity <= 5:
        bad("severity is not a whole number from 1 to 5")
    sentiment = record.get("sentiment")
    if (
        type(sentiment) not in (int, float)
        or not math.isfinite(sentiment)
        or not -1 <= sentiment <= 1
    ):
        bad("sentiment is not a finite number from -1 to 1")
    if type(record.get("needs_review")) is not bool:
        bad("needs_review is not true or false")
    entities = record.get("entities")
    if not isinstance(entities, list) or not all(
        isinstance(x, str) and x.strip() for x in entities
    ):
        bad("entities is not a list of non-blank strings")
    quote = record.get("evidence_quote")
    if not isinstance(quote, str) or not quote.strip():
        bad("evidence quote is blank")
    if quote not in text:
        bad("evidence quote is not an exact piece of the review")
    config = record.get("label_config")
    if not isinstance(config, str) or not config.strip():
        bad("label_config is blank")


def by_rule(intent, severity):
    """The severity the contract's fixed rule gives a label: 1 when the intent reports no problem.

    Applied to every label the pipeline exports (Travis's ruling, 2026-10-05) and, for the second
    reading of a score, to hand labels (spec item 32). It never changes a complaint or a
    cancellation, so it never touches the ranking.
    """
    return 1 if intent in NO_PROBLEM else int(severity)
