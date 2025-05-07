"""Basic arithmetic operations module."""

from typing import Union, List
from decimal import Decimal, getcontext, InvalidOperation

# Set precision for decimal operations
getcontext().prec = 28

Number = Union[int, float, Decimal]

def add(a: Number, b: Number) -> Decimal:
    """Add two numbers with decimal precision."""
    return Decimal(str(a)) + Decimal(str(b))

def subtract(a: Number, b: Number) -> Decimal:
    """Subtract b from a with decimal precision."""
    return Decimal(str(a)) - Decimal(str(b))

def multiply(a: Number, b: Number) -> Decimal:
    """Multiply two numbers with decimal precision."""
    return Decimal(str(a)) * Decimal(str(b))

def divide(a: Number, b: Number) -> Decimal:
    """Divide a by b with decimal precision."""
    if Decimal(str(b)) == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return Decimal(str(a)) / Decimal(str(b))

def power(a: Number, b: Number) -> Decimal:
    """Raise a to the power of b with decimal precision."""
    return Decimal(str(a)) ** Decimal(str(b))

def sum_list(numbers: List[Number]) -> Decimal:
    """Calculate the sum of a list of numbers with decimal precision."""
    total = Decimal('0')
    for num in numbers:
        total += Decimal(str(num))
    return total

def average(numbers: List[Number]) -> Decimal:
    """Calculate the average of a list of numbers with decimal precision."""
    if not numbers:
        raise ValueError("Cannot calculate average of empty list")
    total = sum_list(numbers)
    return total / Decimal(str(len(numbers)))