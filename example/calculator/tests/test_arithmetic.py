"""Tests for the arithmetic module."""

import pytest
from decimal import Decimal
from calculator.arithmetic import (
    add, subtract, multiply, divide, power,
    sum_list, average, Number
)

def test_add():
    """Test addition operations."""
    assert add(1, 2) == Decimal('3')
    assert add(1.5, 2.5) == Decimal('4.0')
    assert add(Decimal('1.1'), Decimal('2.2')) == Decimal('3.3')
    assert add(-1, 1) == Decimal('0')

def test_subtract():
    """Test subtraction operations."""
    assert subtract(5, 3) == Decimal('2')
    assert subtract(3, 5) == Decimal('-2')
    assert subtract(1.5, 0.5) == Decimal('1.0')
    assert subtract(Decimal('2.2'), Decimal('1.1')) == Decimal('1.1')

def test_multiply():
    """Test multiplication operations."""
    assert multiply(2, 3) == Decimal('6')
    assert multiply(2.5, 2) == Decimal('5.0')
    assert multiply(Decimal('1.1'), Decimal('2')) == Decimal('2.2')
    assert multiply(-2, 3) == Decimal('-6')

def test_divide():
    """Test division operations."""
    assert divide(6, 2) == Decimal('3')
    assert divide(5, 2) == Decimal('2.5')
    assert divide(Decimal('2.2'), Decimal('2')) == Decimal('1.1')
    assert divide(-6, 2) == Decimal('-3')
    
    with pytest.raises(ValueError):
        divide(1, 0)

def test_power():
    """Test power operations."""
    assert power(2, 3) == Decimal('8')
    assert power(2, 0.5) == Decimal('1.4142135623730950488016887242097')
    assert power(Decimal('2.2'), Decimal('2')) == Decimal('4.84')
    assert power(2, -1) == Decimal('0.5')

def test_sum_list():
    """Test sum_list operations."""
    assert sum_list([1, 2, 3]) == Decimal('6')
    assert sum_list([1.5, 2.5, 3.0]) == Decimal('7.0')
    assert sum_list([Decimal('1.1'), Decimal('2.2')]) == Decimal('3.3')
    assert sum_list([-1, 1]) == Decimal('0')
    assert sum_list([]) == Decimal('0')

def test_average():
    """Test average operations."""
    assert average([1, 2, 3]) == Decimal('2')
    assert average([1.5, 2.5, 3.0]) == Decimal('2.333333333333333333333333333')
    assert average([Decimal('1.1'), Decimal('2.2')]) == Decimal('1.65')
    assert average([-1, 1]) == Decimal('0')
    
    with pytest.raises(ValueError):
        average([]) 