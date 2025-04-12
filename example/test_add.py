# test_functions.py
import pytest
from functions import add

def test_add_positive_numbers():
    assert add(2, 3) == 5

def test_add_negative_numbers():
    assert add(-2, -3) == -5

def test_add_mixed_numbers():
    assert add(2, -3) == -1
    assert add(-2, 3) == 1

def test_add_zero():
    assert add(0, 5) == 5
    assert add(5, 0) == 5
    assert add(0, 0) == 0

def test_add_large_numbers():
    assert add(1000000, 2000000) == 3000000
    assert add(-1000000, -2000000) == -3000000

def test_add_float_values():
    # If the function needs to support floats, modify it to handle float
    assert add(2.5, 3.1) == 5.6