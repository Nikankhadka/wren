"""Small text normalizations shared by every surface that speaks to a user."""

from __future__ import annotations

import re

# conventions.md 1 bans the em dash repo-wide, and the W-9 reproduction showed a
# prompt rule alone does not hold it: three live drives out of three produced
# "Got it-open Monday" style dashes. Normalizing deterministically in the output
# path is what makes the rule true. Server-authored strings are already written
# with a plain dash, so this only ever touches model prose.
# The pattern names the character by code point: conventions.md 1 bans the
# literal from this repo's source, and this file is not the exception.
_EM_DASH = re.compile(r"\s*\u2014\s*")


def plain_dashes(text: str) -> str:
    """Replace every em dash, and the spacing around it, with a plain dash."""
    return _EM_DASH.sub(" - ", text)
