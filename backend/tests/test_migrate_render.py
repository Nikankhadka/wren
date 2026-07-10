"""Unit tests for the migration runner's fail-closed placeholder substitution."""

from __future__ import annotations

import pytest

from app.core.migrate import _render

SQL = "create role wren_app login password '${WREN_APP_DB_PASSWORD}';"


def test_valid_value_substituted() -> None:
    out = _render(SQL, {"WREN_APP_DB_PASSWORD": "s3cure-Pass_123"})
    assert "s3cure-Pass_123" in out
    assert "${" not in out


def test_missing_var_rejected() -> None:
    with pytest.raises(RuntimeError, match="not set"):
        _render(SQL, {})


@pytest.mark.parametrize("placeholder", ["", "change-me"])
def test_placeholder_defaults_rejected(placeholder: str) -> None:
    with pytest.raises(RuntimeError, match="placeholder"):
        _render(SQL, {"WREN_APP_DB_PASSWORD": placeholder})


@pytest.mark.parametrize(
    "hostile",
    [
        "x'; drop table tenants cascade; --",  # quote breakout
        "abc$$def-ghij",  # dollar-quote breakout
        'pass"word-123',  # double quote
        "back\\slash-123",  # backslash mangling
        "short",  # under min length
    ],
)
def test_unsafe_values_rejected(hostile: str) -> None:
    with pytest.raises(RuntimeError, match="unsafe|placeholder"):
        _render(SQL, {"WREN_APP_DB_PASSWORD": hostile})
