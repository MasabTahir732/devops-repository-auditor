from tiny_math import add


def test_add_negative_and_positive() -> None:
    assert add(-3, 5) == 2


def test_add_zero() -> None:
    assert add(4, 0) == 4
