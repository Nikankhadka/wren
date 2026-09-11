"""W-6: one whole document -> the offering candidates an owner reviews.

The predecessor split each line of two fixed headings ("What we offer",
"Prices") at its first monetary figure and called everything before the cut a
name. On a real owner document - prose, not a spreadsheet - that produced
sentence fragments ("Bowl is", "Pocket both run", "Salads are sold individually
too, mostly"), never a description, and bound whatever number came next to
whatever words came before. This module replaces it.

The shape of the fix is a split of labour, not a better regex:

- **the model identifies**, because recognising that a clause names something
  sellable, and that its price sits in a different sentence, is what a model is
  for;
- **the server counts**, because a language model must never author a monetary
  amount (the deterministic-pricing invariant).

That split is enforced structurally rather than by instruction. Stage 0 indexes
every monetary figure in the document *before the model sees a single token*, so
the set of amounts this module can possibly emit is fixed in advance. The
extraction schema then has no numeric field at all: for money the model can only
hand back a block id - a pointer into that frozen index. There is no field for
an invented number to arrive in.

Stages:

0. ``index_document`` - blocks, figures, hedge and attribution flags. No model.
1. (``structuring.structure_document``, unchanged - the readable sections and
   their own ``figures_preserved`` money guard. This module is a second,
   independent enforcement point, not a relaxation of that one.)
2. ``_identify`` - one model call per segment, returning verbatim spans and
   block ids.
3. ``_resolve`` - verbatim checks, price binding, complexity classification,
   fragment rejection, cross-segment reconciliation. No model.

ponytail: extraction is one model call per ~12k-character segment, run inline
during ingest. A very large document therefore costs several sequential calls
and the owner waits through them. The upgrade path when that hurts is a
background job with the review sheet polling, which O-3's synchronous draft flow
would have to grow first.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.features.business.offering_candidates import normalize_name
from app.features.knowledge.structuring import clean_text, segments
from app.llm.provider import LLMProvider
from app.onboarding.flow import PendingOffering, SourceReference, merge_offerings
from app.pricing.validation_gate import MonetaryFigure, extract_monetary_figures, is_hedged

logger = logging.getLogger("app.knowledge.offering_extraction")

# How far back a reporting verb or an opening quote may sit and still make a
# figure somebody's remembered price rather than the business's own. Wider than
# the pricing gate's hedge window because attribution runs ahead of its figure
# by a clause ("another said the $18 plate"), not by a word.
_ATTRIBUTION_WINDOW = 90

# Reporting verbs and review nouns. Deliberately short: every entry here can
# suppress a real price, so it holds only words that introduce someone else's
# speech, never words that merely appear near opinions ("liked", "rated").
#
# Quotation marks are deliberately NOT a signal here. This kind of document is
# full of scare quotes - a "Pimped Up" pita pocket, chips "described as famous"
# - and treating those as attribution suppressed two real menu prices. A whole
# quoted sentence is caught structurally instead, by _QUOTED_BLOCK_RE.
_ATTRIBUTION_RE = re.compile(
    r"(?:\bsaid\b|\bsays\b|\bwrote\b|\bcalled\s+it\b|\bcomplained\b"
    r"|\bcomment(?:s|ed)?\b|\breview(?:s|er|ers)?\b|\baccording\s+to\b)",
    re.IGNORECASE,
)

# A block that opens inside quotation marks is somebody being quoted in full,
# so any amount in it is their recollection, not the business's price list.
_QUOTED_BLOCK_RE = re.compile(r"^\s*[\"“‘']")

# A range, read forwards from a figure's own text: "$20-$30", "$10-14",
# "$10 to $14". Written this way rather than as a gap between two detected
# figures because the second half of a range routinely drops the currency mark
# ("mostly $10-14"), so the extractor never sees it as a figure at all and a
# pairwise check would read the range as one flat price.
#
# "and" is excluded on purpose: "the Bowl is $27 and comes with pita" is one
# price followed by a clause, not a range.
_RANGE_AFTER_RE = re.compile(r"^\s*(?:-|–|—|to|up\s+to)\s*\$?\s*\d", re.IGNORECASE)

# Wording that makes a single figure a starting point or a rate rather than the
# price of one item.
_OPEN_ENDED_RE = re.compile(
    r"\b(?:from|starting\s+at|starts\s+at|upwards|onwards|each\s+additional"
    r"|mostly|typically|usually|generally|vary|varies)\b",
    re.IGNORECASE,
)
_PER_UNIT_RE = re.compile(r"(?:\bper\b|/)\s*(?:[a-z]{1,12})\b", re.IGNORECASE)

# A name may not open or close on one of these. They are the words a
# first-figure split leaves dangling ("Bowl is", "Pocket both run", "of wrapped
# in. For", "Salads are sold individually too, mostly") and the bare function
# words a model returns when it mistakes a clause for an item ("the").
_DANGLING = frozenset(
    """a an the of for with in on to from at by and or but both is are was were be been
    run runs running cost costs costing start starts price priced prices about around
    roughly approximately mostly typically usually each per plus only just""".split()
)

# Size and portion words that name a variant rather than a thing. "Half plate"
# is not sellable on its own - it needs the item it is half of.
_BARE_MODIFIER_RE = re.compile(
    r"^(?:half|full|small|medium|large|regular|single|double|mini|kids?|"
    r"\d+(?:\.\d+)?\s*(?:g|kg|ml|l|oz|lb|pc|pcs|piece|pieces))\b"
    r"(?:\s+(?:plate|bowl|serve|serving|size|portion|cup|pack))?\s*$",
    re.IGNORECASE,
)

_MAX_NAME_CHARS = 80
_MAX_DESCRIPTION_CHARS = 400
# How far a figure may sit from the name it prices, within one block.
_BINDING_WINDOW = 120


@dataclass(frozen=True)
class SourceBlock:
    """One sentence-sized span of the document, addressable by id.

    Sentence-sized rather than paragraph-sized because a prose menu paragraph
    prices several items in a row ("...the Bowl is $27 and comes with pita on
    the side; for $37, the Super Plate..."). At paragraph granularity every one
    of those figures would look like a competing price for every item in the
    paragraph and the whole passage would flag for review.
    """

    id: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class IndexedFigure:
    """A monetary figure found in the source, with everything the resolver needs
    decided up front."""

    cents: int
    raw: str
    start: int
    hedged: bool
    attributed: bool


@dataclass
class DocumentIndex:
    """Stage 0's output: the complete, frozen set of amounts this document
    contains. Nothing downstream may produce a price that is not in here."""

    text: str
    blocks: list[SourceBlock] = field(default_factory=list)
    figures: list[IndexedFigure] = field(default_factory=list)

    def block(self, block_id: str) -> SourceBlock | None:
        return next((item for item in self.blocks if item.id == block_id), None)

    def figures_in(self, block: SourceBlock) -> list[IndexedFigure]:
        return [item for item in self.figures if block.start <= item.start < block.end]

    def block_at(self, offset: int) -> SourceBlock | None:
        return next(
            (item for item in self.blocks if item.start <= offset < item.end),
            None,
        )


class ExtractedOffering(BaseModel):
    """What the model may say about one item.

    Four string fields, every one of them either a verbatim span of the source
    or a block id. There is no numeric field, and no free-text price field, so
    an invented amount has nowhere to land.
    """

    name_quote: str = Field(description="The item's name, copied exactly from the text")
    base_quote: str = Field(
        default="",
        description=(
            "Only when the name alone is a size or portion ('Half plate'): the item "
            "it belongs to, copied exactly from the text. Empty otherwise."
        ),
    )
    description_quote: str = Field(
        default="",
        description="What the text says this item is, copied exactly. Empty if it says nothing.",
    )
    price_block: str = Field(
        default="",
        description="The id of the block stating this item's price. Empty if none does.",
    )


class ExtractedOfferings(BaseModel):
    offerings: list[ExtractedOffering] = Field(default_factory=list)


_PROMPT = """You are reading a small business's own document to find the things it sells.

The text is numbered by block, one block per line, like `[b7] Hot Chips are $10.`

For each distinct sellable item, return:
- name_quote: the item's name, copied EXACTLY as characters that appear in the text.
- base_quote: only if the name on its own is a size or portion like "Half plate" or
  "Large", the item it is a size of, copied exactly. Otherwise leave empty.
- description_quote: what the text says the item is, copied exactly. Empty if the
  text says nothing about it.
- price_block: the id of the block that states this item's price, e.g. "b7". Empty
  if no block states a price for it.

Rules:
- NEVER write a number, an amount, or a price. For price, return only a block id.
  The server reads the amount from the text itself.
- Copy, do not paraphrase. Every quote must appear verbatim in the text.
- One entry per item that is actually sold. Find items wherever they are described,
  including in ordinary prose sentences and across different sections.
- Join repeated mentions of the same item into one entry.
- Do NOT return: customer reviews or anything someone is quoted as saying, questions
  and answers from an FAQ, delivery fees, memberships, ordering or payment terms,
  price-level symbols, opening hours, addresses, phone numbers, or lists of cuisine
  and category tags.
- A heading or category that groups other items is not itself an item, unless the
  text gives that group its own price.
- Return nothing rather than guessing."""


def index_document(raw_text: str) -> DocumentIndex:
    """Stage 0. The document's blocks and every monetary figure in it.

    Runs before any model call, so the amounts available to the rest of this
    module are fixed before the model has any influence over them.
    """
    text = clean_text(raw_text)
    if not text:
        return DocumentIndex(text="")

    blocks = [
        SourceBlock(id=f"b{index}", start=start, end=end, text=text[start:end].strip())
        for index, (start, end) in enumerate(_block_spans(text))
        if text[start:end].strip()
    ]
    figures = [
        IndexedFigure(
            cents=figure.cents,
            raw=figure.raw,
            start=figure.start,
            hedged=is_hedged(text, figure),
            attributed=_is_attributed(text, figure, blocks),
        )
        for figure in extract_monetary_figures(text)
    ]
    return DocumentIndex(text=text, blocks=blocks, figures=figures)


def _block_spans(text: str) -> list[tuple[int, int]]:
    """Sentence-sized spans, as (start, end) offsets into ``text``.

    Splits on line breaks and on sentence and clause punctuation, because a
    prose paragraph carries several priced items and each needs its own price
    context. Offsets are kept (rather than the substrings alone) so a figure's
    position from ``extract_monetary_figures`` maps back to its block.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"(?:\n+|(?<=[.;:!?])\s+)", text):
        if match.start() > start:
            spans.append((start, match.start()))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _is_attributed(text: str, figure: MonetaryFigure, blocks: list[SourceBlock]) -> bool:
    """Is this figure somebody's remembered price rather than the business's own?

    The fixture's "another said the $18 plate..." and its quoted review lines
    are the case: real amounts, in the document, that price nothing the owner
    sells. ``is_hedged`` catches "around $18" but not the bare reported one.

    Two signals: a reporting verb in the run-up to the figure, or the figure
    sitting inside a block that is itself a quotation.
    """
    if figure.start < 0:
        return False
    before = text[max(0, figure.start - _ATTRIBUTION_WINDOW) : figure.start]
    if _ATTRIBUTION_RE.search(before):
        return True
    block = next((item for item in blocks if item.start <= figure.start < item.end), None)
    return bool(block and _QUOTED_BLOCK_RE.match(block.text))


async def extract_offerings(
    raw_text: str, *, provider: LLMProvider, document_id: UUID
) -> tuple[list[PendingOffering], str]:
    """The whole document -> reviewable candidates, and how complete the read was.

    Returns ``(candidates, status)`` where status is ``full`` when every segment
    was identified and resolved, ``partial`` when some segment failed, and
    ``failed`` when none succeeded. A failure never falls back to splitting
    lines at their first figure - that is the behaviour this module replaces -
    it simply yields fewer candidates and says so, leaving the readable sections
    as the owner's route to the source. ``document_id`` is stamped onto every
    candidate as its sole supporting document (W-11), so a later replacement of
    this document knows which candidates depended on it.
    """
    index = index_document(raw_text)
    if not index.text:
        return [], "full"

    resolved: list[PendingOffering] = []
    failures = 0
    attempts = 0
    for segment_blocks in _segment_blocks(index):
        attempts += 1
        try:
            identified = await _identify(segment_blocks, provider=provider)
        except Exception:
            logger.warning("offering extraction failed for a segment", exc_info=True)
            failures += 1
            continue
        resolved.extend(
            _resolve(identified, index=index, blocks=segment_blocks, document_id=document_id)
        )

    if failures and failures == attempts:
        return [], "failed"
    # Reconciliation is across segments, not within one: a 12k-character
    # boundary can fall between an item's name and the sentence pricing it, so
    # the same item can arrive twice from two calls.
    candidates = _reconcile(resolved)
    _attach_possible_matches(candidates)
    return candidates, "partial" if failures else "full"


def _segment_blocks(index: DocumentIndex) -> list[list[SourceBlock]]:
    """The document's blocks, grouped into model-sized segments.

    Reuses ``structuring.segments`` so both passes cut the document the same
    way, then maps each segment back to the blocks it covers.
    """
    grouped: list[list[SourceBlock]] = []
    cursor = 0
    for segment in segments(index.text):
        found = index.text.find(segment, cursor)
        start = found if found >= 0 else cursor
        end = start + len(segment)
        cursor = end
        covered = [item for item in index.blocks if start <= item.start < end]
        if covered:
            grouped.append(covered)
    return grouped or ([index.blocks] if index.blocks else [])


async def _identify(blocks: list[SourceBlock], *, provider: LLMProvider) -> list[ExtractedOffering]:
    """Stage 2. One model call over one segment, block ids included."""
    numbered = "\n".join(f"[{item.id}] {item.text}" for item in blocks)
    result = await provider.extract(
        system_prompt=_PROMPT, user_input=numbered, schema=ExtractedOfferings
    )
    return list(result.offerings)


def _resolve(
    identified: list[ExtractedOffering],
    *,
    index: DocumentIndex,
    blocks: list[SourceBlock],
    document_id: UUID,
) -> list[PendingOffering]:
    """Stage 3. Verified names, source-derived prices, flagged ambiguity."""
    segment_text = "\n".join(item.text for item in blocks)
    names = [_compose_name(item, segment_text=segment_text) for item in identified]
    resolved: list[PendingOffering] = []
    for candidate, name in zip(identified, names, strict=True):
        if name is None:
            continue
        description = _verified_span(candidate.description_quote, segment_text)
        price_cents, price_note, needs_review = _resolve_price(
            candidate, name=name, index=index, other_names=[item for item in names if item != name]
        )
        resolved.append(
            PendingOffering(
                name=name,
                description=description[:_MAX_DESCRIPTION_CHARS],
                price_cents=price_cents,
                price_note=price_note,
                needs_review=needs_review,
                sources=["document"],
                supporting_document_ids=[document_id],
                source_references=_source_references(candidate, name, description, index),
            )
        )
    return resolved


def _source_references(
    candidate: ExtractedOffering, name: str, description: str, index: DocumentIndex
) -> list[SourceReference]:
    """Keep the verified blocks that support the candidate on the wire."""
    fields_by_block: dict[str, set[Literal["name", "description", "price"]]] = {}
    supported_quotes: tuple[tuple[Literal["name", "description", "price"], str], ...] = (
        ("name", name),
        ("description", description),
    )
    for supported_field, quote in supported_quotes:
        if quote:
            block = next(
                (item for item in index.blocks if _find_position(item.text, quote) >= 0), None
            )
            if block is not None:
                fields_by_block.setdefault(block.id, set()).add(supported_field)
    if candidate.price_block and (block := index.block(candidate.price_block)) is not None:
        fields_by_block.setdefault(block.id, set()).add("price")
    return [
        SourceReference(
            block=block_id,
            excerpt=index.block(block_id).text[:2000],  # type: ignore[union-attr]
            supported_fields=sorted(fields),
        )
        for block_id, fields in fields_by_block.items()
    ]


def _compose_name(candidate: ExtractedOffering, *, segment_text: str) -> str | None:
    """The candidate's display name, or None when it does not name a thing.

    The name is the model's span taken verbatim - the source already writes
    complete noun phrases ("a Larnaca pocket"), and rewriting them would be
    authoring. The one exception is a bare size ("Half plate"), which names a
    variant rather than an item and is only usable once joined to the item it
    is a size of. A bare size with no resolvable base is dropped rather than
    guessed at: "Half plate" alone could be half of anything.
    """
    name = _verified_span(candidate.name_quote, segment_text)
    if not name or _is_fragment(name):
        return None
    if _BARE_MODIFIER_RE.match(name):
        base = _verified_span(candidate.base_quote, segment_text)
        if not base or _is_fragment(base):
            return None
        name = f"{base} - {name}"
    return name[:_MAX_NAME_CHARS]


def _verified_span(quote: str, source: str) -> str:
    """The quote, but only if the source actually contains it.

    A model that paraphrases where it was told to copy is not quoting, and a
    candidate built on a paraphrase is not safe to trust for anything else it
    says about that item either. Whitespace is normalised on both sides because
    a PDF wraps mid-phrase; nothing else is.
    """
    cleaned = re.sub(r"\s+", " ", quote or "").strip().strip("\"'“”")
    if not cleaned:
        return ""
    return cleaned if cleaned.casefold() in re.sub(r"\s+", " ", source).casefold() else ""


def _is_fragment(name: str) -> bool:
    """Is this a piece of a sentence rather than the name of a thing?

    Catches the whole class the first-figure split produced: a name that opens
    or closes on a function word or a dangling verb ("Bowl is", "Pocket both
    run", "Salads are sold individually too, mostly"), one that runs across a
    sentence boundary ("of wrapped in. For"), and one long enough to be prose.
    """
    stripped = name.strip().strip(",;:")
    if not stripped or len(stripped) > _MAX_NAME_CHARS:
        return True
    if not any(char.isalpha() for char in stripped):
        return True
    if re.search(r"[.!?]\s+\S", stripped):
        return True
    words = [word.strip(",.;:()") for word in stripped.split()]
    words = [word for word in words if word]
    if not words:
        return True
    return words[0].casefold() in _DANGLING or words[-1].casefold() in _DANGLING


def _resolve_price(
    candidate: ExtractedOffering,
    *,
    name: str,
    index: DocumentIndex,
    other_names: list[str | None],
) -> tuple[int | None, str, bool]:
    """The item's price in integer cents, or the source's wording and a flag.

    Every amount here comes out of stage 0's index, keyed by the block id the
    model pointed at. Nothing the model wrote is parsed for a number, so there
    is no path by which a model-authored figure becomes a price.
    """
    block = index.block(candidate.price_block) if candidate.price_block else None
    if block is None:
        return None, "", False

    figures = index.figures_in(block)
    if not figures:
        return None, "", False
    if any(figure.hedged or figure.attributed for figure in figures):
        # An estimate or somebody's recollection. Keep neither the number nor a
        # review flag - the document never claimed this was the item's price.
        return None, "", False

    if _is_complex(block, figures):
        # A range, a "from" price, or a rate. The existing offering row holds
        # one flat amount and cannot carry the meaning, so the source's own
        # wording goes to the owner instead of a number picked out of it.
        return None, block.text[:_MAX_DESCRIPTION_CHARS], True

    figure = _bound_figure(block, figures, name=name, other_names=other_names)
    if figure is None:
        return None, block.text[:_MAX_DESCRIPTION_CHARS], True
    return figure.cents, "", False


def _is_complex(block: SourceBlock, figures: list[IndexedFigure]) -> bool:
    """Does this block state something other than one flat price?"""
    if _OPEN_ENDED_RE.search(block.text) or _PER_UNIT_RE.search(block.text):
        return True
    return any(
        _RANGE_AFTER_RE.match(block.text[figure.start - block.start + len(figure.raw) :])
        for figure in figures
    )


def _bound_figure(
    block: SourceBlock,
    figures: list[IndexedFigure],
    *,
    name: str,
    other_names: list[str | None],
) -> IndexedFigure | None:
    """The one figure that prices this item, or None when that is ambiguous.

    A single figure in the block prices it. With several ("Hot Chips ($10...)
    and Six Falafel ($10.90...)") the nearest one wins, but only when no other
    item's name sits between the two - otherwise the figure belongs to that
    other item and this one has no unambiguous price.
    """
    if len(figures) == 1:
        return figures[0]
    position = _find_position(block.text, name)
    if position < 0:
        return None
    nearest = min(figures, key=lambda item: abs(item.start - block.start - position))
    offset = nearest.start - block.start
    low, high = sorted((position, offset))
    if high - low > _BINDING_WINDOW:
        return None
    between = block.text[low:high]
    if any(other and _find_position(between, other) >= 0 for other in other_names):
        return None
    return nearest


def _find_position(haystack: str, needle: str) -> int:
    return haystack.casefold().find(needle.casefold())


def _reconcile(candidates: list[PendingOffering]) -> list[PendingOffering]:
    """Repeated evidence about one item, joined into one row.

    Uses ``merge_offerings`` - the same precedence the onboarding record applies
    when an owner-typed name meets a document candidate - so one policy governs
    every merge in the system.
    """
    merged: dict[str, PendingOffering] = {}
    order: list[str] = []
    for item in candidates:
        key = normalize_name(item.name)
        if key not in merged:
            merged[key] = item
            order.append(key)
            continue
        merged[key] = merge_offerings(merged[key], item)
    return [merged[key] for key in order]


def _attach_possible_matches(candidates: list[PendingOffering]) -> None:
    """Flag names that might be the same item, without merging them.

    "coffe" and "coffee drinks" are a decision for the owner, not for this
    module: one is a typo for the other, or they are a specific drink and the
    category above it, and nothing in the text settles which. Merging on
    similarity would silently delete a real item, so similar names stay two
    rows carrying a pointer at each other. W-8 turns these into a choice.
    """
    for first, second in ((a, b) for a in candidates for b in candidates if a is not b):
        if _is_possible_match(first.name, second.name):
            first.possible_matches = sorted({*first.possible_matches, second.candidate_id})


def _is_possible_match(left: str, right: str) -> bool:
    first, second = normalize_name(left), normalize_name(right)
    if not first or not second or first == second:
        return False
    # One name contained in the other is the category/product case
    # ("Pita Pocket" in "Sabbaba Pita Pocket"). A near-spelling is the typo case
    # ("coffe" / "coffee drinks"), compared on first words so a shared head word
    # with extra qualifiers still pairs.
    if f" {first} " in f" {second} " or f" {second} " in f" {first} ":
        return True
    head, other_head = first.split(" ")[0], second.split(" ")[0]
    return len(head) > 3 and len(other_head) > 3 and _close(head, other_head)


def _close(left: str, right: str) -> bool:
    """One edit apart, by the classic single-row Levenshtein."""
    if abs(len(left) - len(right)) > 1:
        return False
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1] <= 1
