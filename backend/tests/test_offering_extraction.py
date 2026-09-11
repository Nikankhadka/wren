"""W-6: the whole document -> offering candidates, and the money rule on that path.

The fixture is the real thing. ``Sabbaba_Business_Profile.pdf`` is the document
behind the founder's 40-row walkthrough report - six pages of prose about a
Bondi Junction restaurant, roughly twenty sellable items scattered through a
document that is mostly reviews, FAQ answers and platform trivia. It is the
source that produced "Bowl is" and "Pocket both run" from the predecessor's
first-figure line split, so it is what the replacement has to be right about.

Two properties are pinned here, and they are different in kind:

- **the money rule**, which must hold absolutely: no ``price_cents`` may exist
  that did not come out of ``extract_monetary_figures`` on the document's own
  text. That is a structural guarantee (stage 0 indexes every figure before the
  model runs, and the schema has no numeric field), and it is tested as one.
- **extraction quality**, which is best-effort: the model has to identify items
  in prose, and it will not always. Those tests use a fake provider, so they pin
  *this module's* resolution of a given identification, never a model's skill.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.features.knowledge import offering_extraction as extraction
from app.features.knowledge.offering_extraction import (
    ExtractedOffering,
    extract_offerings,
    index_document,
)
from app.llm.provider import SchemaT
from app.onboarding.flow import PendingOffering
from app.pricing.validation_gate import extract_monetary_figures
from tests.fakes import BaseFakeProvider

FIXTURE = Path(__file__).parent / "fixtures" / "sabbaba_profile.txt"
SOURCE = FIXTURE.read_text()
DOCUMENT_ID = uuid4()


@pytest.fixture(scope="module")
def index() -> extraction.DocumentIndex:
    return index_document(SOURCE)


def block_id(index: extraction.DocumentIndex, fragment: str) -> str:
    """The id of the block containing ``fragment`` - how a model would point at
    a price without writing one."""
    block = next((item for item in index.blocks if fragment in item.text), None)
    assert block is not None, f"fixture no longer contains {fragment!r}"
    return block.id


class IdentifyFake(BaseFakeProvider):
    """Returns a fixed identification, so these tests assert on this module's
    resolution of it rather than on a model's reading of prose."""

    def __init__(self, offerings: list[dict[str, str]]) -> None:
        self.offerings = offerings
        self.calls = 0

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        self.calls += 1
        visible = [
            item
            for item in self.offerings
            if not item.get("price_block") or f"[{item['price_block']}]" in user_input
        ]
        return schema.model_validate({"offerings": visible})


class FailingFake(BaseFakeProvider):
    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        raise RuntimeError("provider is down")


async def resolve(offerings: list[dict[str, str]]) -> dict[str, PendingOffering]:
    candidates, _ = await extract_offerings(
        SOURCE, provider=IdentifyFake(offerings), document_id=DOCUMENT_ID
    )
    return {item.name: item for item in candidates}


# --------------------------------------------------------------------------
# The money rule
# --------------------------------------------------------------------------


def test_the_extraction_schema_has_no_field_a_model_could_put_a_number_in() -> None:
    """The structural half of the money rule: not "the model is told not to",
    but "there is nowhere for it to go"."""
    for name, field in ExtractedOffering.model_fields.items():
        assert field.annotation is str, f"{name} is not a string field"


@pytest.mark.asyncio
async def test_no_price_exists_that_is_not_a_figure_in_the_source() -> None:
    """The regression that guards the deterministic-pricing invariant on this
    path, analogous to the figure-provenance tests in test_agent_graph.py.

    The fake points every item at a real block, and one of them additionally
    tries to smuggle an amount through the only channel it has - the quoted
    spans. No amount may reach a price except through the source index.
    """
    index = index_document(SOURCE)
    allowed = {figure.cents for figure in extract_monetary_figures(index.text)}
    candidates, _ = await extract_offerings(
        SOURCE,
        provider=IdentifyFake(
            [
                {"name_quote": "Bowl", "price_block": block_id(index, "the Bowl is")},
                {"name_quote": "Hot Chips", "price_block": block_id(index, "Hot Chips")},
                {
                    "name_quote": "Six Falafel",
                    "description_quote": "only $999 today",
                    "price_block": block_id(index, "89% liked"),
                },
            ]
        ),
        document_id=DOCUMENT_ID,
    )
    priced = [item.price_cents for item in candidates if item.price_cents is not None]
    assert priced, "expected at least one resolved price"
    assert all(cents in allowed for cents in priced)
    assert 99900 not in priced


@pytest.mark.asyncio
async def test_a_paraphrased_quote_is_not_trusted() -> None:
    """A model told to copy that paraphrases instead is not quoting, so nothing
    it says about that item is safe to build on."""
    index = index_document(SOURCE)
    resolved = await resolve(
        [{"name_quote": "Falafel Bowl Deluxe", "price_block": block_id(index, "the Bowl is")}]
    )
    assert resolved == {}


@pytest.mark.asyncio
async def test_a_price_from_a_review_never_becomes_an_offering_price() -> None:
    """The fixture prices the plate twice: $20-$30 on the menu, and $18 in two
    customer reviews. Neither review amount may price anything."""
    index = index_document(SOURCE)
    resolved = await resolve(
        [{"name_quote": "plate", "price_block": block_id(index, "another said the $18")}]
    )
    assert resolved["plate"].price_cents is None


def test_hedged_and_attributed_figures_are_flagged_at_index_time(
    index: extraction.DocumentIndex,
) -> None:
    by_context = {figure.start: figure for figure in index.figures if figure.cents == 1800}
    assert by_context, "fixture no longer contains the $18 review prices"
    assert all(figure.hedged or figure.attributed for figure in by_context.values())


def test_scare_quotes_do_not_suppress_a_real_price(index: extraction.DocumentIndex) -> None:
    """This document is full of scare quotes - a "Pimped Up" pocket, chips
    "described as famous". Treating those as attribution silently dropped two
    real menu prices, so quoting alone is deliberately not a signal."""
    block = index.block(block_id(index, "Hot Chips"))
    assert block is not None
    figures = index.figures_in(block)
    assert figures and not any(item.attributed or item.hedged for item in figures)


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fragment",
    ["Bowl is", "the", "Pocket both run", "Salads are sold individually too, mostly"],
)
async def test_sentence_fragments_never_become_offerings(fragment: str) -> None:
    """The exact class the founder reported. Each of these is a real substring
    of the fixture that the predecessor emitted as an offering name."""
    index = index_document(SOURCE)
    resolved = await resolve(
        [{"name_quote": fragment, "price_block": block_id(index, "the Bowl is")}]
    )
    assert resolved == {}


# A tabular menu, the shape the Sabbaba fixture is not: sizes listed under the
# item they are sizes of. This is where the bare-modifier rule earns its keep.
_SIZED_MENU = """CHICKEN OVER RICE
Half plate - $16.50
Full plate - $22.00

LAMB GYRO
Half plate - $17.50
"""


async def resolve_in(source: str, offerings: list[dict[str, str]]) -> dict[str, PendingOffering]:
    candidates, _ = await extract_offerings(
        source, provider=IdentifyFake(offerings), document_id=DOCUMENT_ID
    )
    return {item.name: item for item in candidates}


@pytest.mark.asyncio
async def test_a_bare_size_is_joined_to_the_item_it_is_a_size_of() -> None:
    """ "Half plate" names a variant, not a thing - on this menu it could be half
    a chicken plate or half a gyro plate. It is only usable once bound to the
    item, and the server composes the name from two verified spans; the model
    never writes the joined string."""
    index = index_document(_SIZED_MENU)
    resolved = await resolve_in(
        _SIZED_MENU,
        [
            {
                "name_quote": "Half plate",
                "base_quote": "CHICKEN OVER RICE",
                "price_block": block_id(index, "Half plate - $16.50"),
            }
        ],
    )
    assert "CHICKEN OVER RICE - Half plate" in resolved
    assert resolved["CHICKEN OVER RICE - Half plate"].price_cents == 1650


@pytest.mark.asyncio
async def test_a_bare_size_with_no_resolvable_base_is_dropped_not_guessed() -> None:
    """Half of what? This menu has two candidate bases and the span names
    neither, so nothing is invented - the row simply does not appear."""
    index = index_document(_SIZED_MENU)
    resolved = await resolve_in(
        _SIZED_MENU,
        [{"name_quote": "Half plate", "price_block": block_id(index, "Half plate - $16.50")}],
    )
    assert resolved == {}


# --------------------------------------------------------------------------
# Prices: flat, complex, absent
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_single_flat_price_resolves() -> None:
    index = index_document(SOURCE)
    resolved = await resolve(
        [
            {
                "name_quote": "Bowl",
                "description_quote": "comes with pita on the side",
                "price_block": block_id(index, "the Bowl is"),
            }
        ]
    )
    assert resolved["Bowl"].price_cents == 2700
    assert resolved["Bowl"].description == "comes with pita on the side"
    assert resolved["Bowl"].needs_review is False


@pytest.mark.asyncio
async def test_two_items_sharing_one_range_stay_two_flagged_rows() -> None:
    """ "The Plate and Pita Pocket both run $20-$30" - two separately named
    items, one range. Neither gets a number picked out of the range, both keep
    the source's wording, and no composite fragment is created."""
    index = index_document(SOURCE)
    shared = block_id(index, "both run")
    resolved = await resolve(
        [
            {"name_quote": "Plate", "price_block": shared},
            {"name_quote": "Pita", "price_block": shared},
        ]
    )
    assert set(resolved) == {"Plate", "Pita"}
    for item in resolved.values():
        assert item.price_cents is None
        assert item.needs_review is True
        assert "$20–$30" in item.price_note


@pytest.mark.asyncio
async def test_a_range_whose_second_half_drops_the_currency_mark_is_still_a_range() -> None:
    """ "mostly $10-14" - the extractor only ever sees "$10", so a check that
    compared two detected figures would read this as one flat price and put
    every salad on the menu at $10."""
    index = index_document(SOURCE)
    resolved = await resolve(
        [
            {"name_quote": "plain pickles", "price_block": block_id(index, "Salads are sold")},
        ]
    )
    item = resolved["plain pickles"]
    assert item.price_cents is None
    assert item.needs_review is True
    assert "$10–14" in item.price_note


@pytest.mark.asyncio
async def test_an_absent_price_is_not_the_same_as_an_ambiguous_one() -> None:
    """The fixture names chicken shawarma with no price at all. Silence is an
    ordinary thing for a source to do and is not a review flag."""
    resolved = await resolve([{"name_quote": "chicken shawarma"}])
    assert resolved["chicken shawarma"].price_cents is None
    assert resolved["chicken shawarma"].needs_review is False


@pytest.mark.asyncio
async def test_neighbouring_items_in_one_sentence_keep_their_own_prices() -> None:
    """ "Hot Chips ($10...) and Six Falafel ($10.90...)" - the nearest figure
    wins, but only because no other item's name sits between them."""
    index = index_document(SOURCE)
    resolved = await resolve(
        [
            {"name_quote": "Hot Chips", "price_block": block_id(index, "Hot Chips")},
            {"name_quote": "Six Falafel", "price_block": block_id(index, "89% liked")},
        ]
    )
    assert resolved["Hot Chips"].price_cents == 1000
    assert resolved["Six Falafel"].price_cents == 1090


# --------------------------------------------------------------------------
# Reconciliation, matches, failure
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_same_item_found_twice_becomes_one_row() -> None:
    """A 12k-character segment boundary can fall between an item's name and the
    sentence pricing it, so reconciliation is across segments, not within one."""
    index = index_document(SOURCE)
    resolved = await resolve(
        [
            {"name_quote": "Bowl"},
            {"name_quote": "Bowl", "price_block": block_id(index, "the Bowl is")},
        ]
    )
    assert len([name for name in resolved if name == "Bowl"]) == 1
    assert resolved["Bowl"].price_cents == 2700


@pytest.mark.asyncio
async def test_similar_names_are_suggested_not_merged() -> None:
    """A category and a specific item under it. Merging on similarity would
    silently delete a real offering, so both survive pointing at each other."""
    index = index_document(SOURCE)
    resolved = await resolve(
        [
            {"name_quote": "Larnaca pocket", "price_block": block_id(index, "Larnaca pocket")},
            {
                "name_quote": "Sabbaba Pita Pocket",
                "price_block": block_id(index, "Sabbaba Pita Pocket"),
            },
            {"name_quote": "Tunisian pocket", "price_block": block_id(index, "Tunisian pocket")},
        ]
    )
    assert len(resolved) == 3
    assert resolved["Larnaca pocket"].price_cents == 1990
    assert resolved["Sabbaba Pita Pocket"].price_cents == 2000


def test_close_names_pair_and_distinct_ones_do_not() -> None:
    assert extraction._is_possible_match("coffe", "coffee drinks")
    assert extraction._is_possible_match("Pita Pocket", "Sabbaba Pita Pocket")
    assert not extraction._is_possible_match("Plate", "Bowl")
    assert not extraction._is_possible_match("Plate", "Plate")


@pytest.mark.asyncio
async def test_extraction_failure_yields_no_candidates_and_says_so() -> None:
    """A failure never falls back to splitting lines at their first figure -
    that is the behaviour being replaced. It yields nothing and reports it, so
    the review sheet can say the read was incomplete instead of showing a
    truncated list that looks whole."""
    candidates, status = await extract_offerings(
        SOURCE, provider=FailingFake(), document_id=DOCUMENT_ID
    )
    assert candidates == []
    assert status == "failed"


@pytest.mark.asyncio
async def test_an_empty_document_is_not_an_error() -> None:
    candidates, status = await extract_offerings(
        "   \n\n ", provider=FailingFake(), document_id=DOCUMENT_ID
    )
    assert (candidates, status) == ([], "full")


@pytest.mark.asyncio
async def test_the_whole_document_is_read_not_two_headings() -> None:
    """The predecessor only ever looked under "What we offer" and "Prices".
    This fixture has neither heading, and every price in it lives in prose."""
    index = index_document(SOURCE)
    assert "What we offer" not in SOURCE and "Prices" not in SOURCE
    assert len(index.figures) > 10
