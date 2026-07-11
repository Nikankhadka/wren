"""T-018: the price-provenance validation gate (pure logic half).

Deterministic - no LLM imports in this module, same rule as the engine.
``validate`` extracts every monetary figure from a draft response (currency
patterns, "N dollars" phrasings, and spelled-out amounts like "twelve
hundred") and requires each one to reconcile exactly to pricing-engine
output (unit amounts, line totals, subtotal, tax, total) or to DB-sourced
provenance (catalog ``price_cents`` the Recommendation Agent fetched). Any
unmatched figure is a violation - including a customer's own stated budget
restated by the model, which is deliberate: generated text states no
amounts at all, the QuoteCard does.

The graph half (app/agents/price_gate.py) runs this after Quoting and
Recommendation: one redraft with the violations listed, then escalation
with reason ``price_provenance``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_CURRENCY_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?")
_DOLLARS_WORD_RE = re.compile(
    r"\b(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?\s*(?:dollars?|bucks?|usd)\b", re.IGNORECASE
)

_UNITS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000}
_CURRENCY_WORDS = {"dollar", "dollars", "buck", "bucks", "usd"}
_NUMBER_WORDS = _UNITS.keys() | _TENS.keys() | _SCALES.keys()

_WORD_RE = re.compile(r"[a-z]+(?:-[a-z]+)?|\S", re.IGNORECASE)


@dataclass(frozen=True)
class MonetaryFigure:
    raw: str
    cents: int


def _to_cents(whole: str, fraction: str | None) -> int:
    cents = int(whole.replace(",", "")) * 100
    if fraction:
        cents += int(fraction.ljust(2, "0"))
    return cents


def _word_value(words: list[str]) -> int:
    """Standard spelled-number evaluation: 'twelve hundred' -> 1200,
    'one thousand two hundred fifty' -> 1250."""
    total = 0
    current = 0
    for word in words:
        if word in _UNITS:
            current += _UNITS[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word == "hundred":
            current = max(current, 1) * 100
        elif word == "thousand":
            total += max(current, 1) * 1000
            current = 0
    return total + current


def _spelled_figures(text: str) -> list[MonetaryFigure]:
    tokens = [(match.group(0), match.start()) for match in _WORD_RE.finditer(text)]
    figures: list[MonetaryFigure] = []
    i = 0
    while i < len(tokens):
        # Collect a maximal run of number words ("and" allowed inside).
        run: list[str] = []
        start = i
        while i < len(tokens):
            word = tokens[i][0].lower()
            parts = word.split("-")
            if all(part in _NUMBER_WORDS for part in parts):
                run.extend(parts)
                i += 1
            elif (
                word == "and"
                and run
                and i + 1 < len(tokens)
                and (tokens[i + 1][0].lower() in _NUMBER_WORDS)
            ):
                i += 1
            else:
                break
        if not run:
            i += 1
            continue
        followed_by_currency = i < len(tokens) and tokens[i][0].lower() in _CURRENCY_WORDS
        has_scale = any(word in _SCALES for word in run)
        # A bare unit ("five") is almost never money; require either a scale
        # word ("twelve hundred") or an explicit currency word ("five bucks").
        if followed_by_currency or has_scale:
            raw_start = tokens[start][1]
            raw_end = (
                tokens[i][1] + len(tokens[i][0])
                if followed_by_currency
                else (tokens[i - 1][1] + len(tokens[i - 1][0]))
            )
            figures.append(
                MonetaryFigure(raw=text[raw_start:raw_end], cents=_word_value(run) * 100)
            )
    return figures


def extract_monetary_figures(text: str) -> list[MonetaryFigure]:
    figures = [
        MonetaryFigure(raw=match.group(0), cents=_to_cents(match.group(1), match.group(2)))
        for match in _CURRENCY_RE.finditer(text)
    ]
    figures += [
        MonetaryFigure(raw=match.group(0), cents=_to_cents(match.group(1), match.group(2)))
        for match in _DOLLARS_WORD_RE.finditer(text)
        # "$120 dollars" would double-report; the currency regex already got it.
        if not any(match.group(1) in figure.raw for figure in figures)
    ]
    figures += _spelled_figures(text)
    return figures


def allowed_cents(engine_quote: dict[str, Any] | None, provenance: Iterable[int]) -> set[int]:
    allowed = set(provenance)
    if engine_quote is not None:
        for item in engine_quote.get("line_items", []):
            allowed.add(int(item["unit_amount_cents"]))
            allowed.add(int(item["line_total_cents"]))
        allowed.add(int(engine_quote["subtotal_cents"]))
        allowed.add(int(engine_quote["tax_cents"]))
        allowed.add(int(engine_quote["total_cents"]))
    return allowed


def validate(
    draft_response: str,
    engine_quote: dict[str, Any] | None,
    provenance: Iterable[int] = (),
) -> list[str]:
    """Empty list = ok. Each violation names the offending figure so the
    producing node can be re-prompted with it."""
    allowed = allowed_cents(engine_quote, provenance)
    return [
        f"'{figure.raw}' does not reconcile to any engine-computed or database-sourced amount"
        for figure in extract_monetary_figures(draft_response)
        if figure.cents not in allowed
    ]
