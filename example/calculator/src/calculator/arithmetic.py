"""Basic arithmetic operations module."""

from typing import Union, List
from decimal import Decimal, getcontext

# Set precision for decimal operations
getcontext().prec = 28

Number = Union[int, float, Decimal]

def add(a: Number, b: Number) -> Decimal:
    """Add two numbers."""
    return Decimal(str(a)) + Decimal(str(b))

def subtract(a: Number, b: Number) -> Decimal:
    """Subtract b from a."""
    return Decimal(str(a)) - Decimal(str(b))

def multiply(a: Number, b: Number) -> Decimal:
    """Multiply two numbers."""
    return Decimal(str(a)) * Decimal(str(b))

def divide(a: Number, b: Number) -> Decimal:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Division by zero")
    return Decimal(str(a)) / Decimal(str(b))

def power(a: Number, b: Number) -> Decimal:
    """Raise a to the power of b."""
    return Decimal(str(a)) ** Decimal(str(b))

def sum_list(numbers: List[Number]) -> Decimal:
    """Sum a list of numbers."""
    return sum(Decimal(str(n)) for n in numbers)

def average(numbers: List[Number]) -> Decimal:
    """Calculate the average of a list of numbers."""
    if not numbers:
        raise ValueError("Cannot calculate average of empty list")
    return sum_list(numbers) / Decimal(str(len(numbers))) 