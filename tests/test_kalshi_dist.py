"""Tests for Kalshi bracket sub-title parsing.

These cases are the real strings observed from KXINXY / KXNASDAQ100Y in the
production API — they encode the only contract about Kalshi's response format
this codebase depends on.
"""
from market_predict.transforms.kalshi_dist import parse_bracket


def test_above():
    assert parse_bracket("9,000.01 or above") == ("above", 9000.01, None)


def test_below():
    assert parse_bracket("3,999.99 or below") == ("below", None, 3999.99)


def test_between():
    assert parse_bracket("8,800 to 9,000") == ("between", 8800.0, 9000.0)


def test_between_with_decimals():
    assert parse_bracket("8,400 to 8,599.99") == ("between", 8400.0, 8599.99)


def test_unknown_falls_through():
    assert parse_bracket("garbage input") == ("unknown", None, None)


def test_empty_string():
    assert parse_bracket("") == ("unknown", None, None)
