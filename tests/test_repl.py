import pytest

from src.repl import _parse_indices


def test_parse_indices_single_number():
    assert _parse_indices("3") == [3]


def test_parse_indices_comma_list():
    assert _parse_indices("1,3,5") == [1, 3, 5]


def test_parse_indices_space_list():
    assert _parse_indices("1 3 5") == [1, 3, 5]


def test_parse_indices_range():
    assert _parse_indices("1-5") == [1, 2, 3, 4, 5]


def test_parse_indices_reversed_range_normalizes():
    assert _parse_indices("5-1") == [1, 2, 3, 4, 5]


def test_parse_indices_mixed_list_and_range():
    assert _parse_indices("1-3,5,8-10") == [1, 2, 3, 5, 8, 9, 10]


def test_parse_indices_invalid_raises_value_error():
    with pytest.raises(ValueError):
        _parse_indices("abc")
