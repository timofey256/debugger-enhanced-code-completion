"""Tests for the expression module."""

import pytest
from decimal import Decimal
from calculator.expression import ExpressionEvaluator, evaluate_expression, parse_expression

def test_parse_expression():
    """Test expression parsing."""
    assert parse_expression("1 + 2") == "1 + 2"
    assert parse_expression("(1 + 2) * 3") == "(1 + 2) * 3"
    assert parse_expression("add(1, 2)") == "add(1, 2)"
    
    with pytest.raises(ValueError):
        parse_expression("1 + ")  # Invalid syntax

def test_evaluate_expression():
    """Test expression evaluation."""
    assert evaluate_expression("1 + 2") == Decimal('3')
    assert evaluate_expression("(1 + 2) * 3") == Decimal('9')
    assert evaluate_expression("add(1, 2)") == Decimal('3')
    
    # Test with variables
    variables = {'x': 5, 'y': 3}
    assert evaluate_expression("x + y", variables) == Decimal('8')
    assert evaluate_expression("x * y", variables) == Decimal('15')
    
    with pytest.raises(ValueError):
        evaluate_expression("undefined_var + 1")  # Undefined variable

def test_expression_evaluator():
    """Test ExpressionEvaluator class."""
    evaluator = ExpressionEvaluator()
    
    # Test basic operations
    assert evaluator.evaluate("1 + 2") == Decimal('3')
    assert evaluator.evaluate("(1 + 2) * 3") == Decimal('9')
    
    # Test variables
    evaluator.set_variable('x', 5)
    evaluator.set_variable('y', 3)
    assert evaluator.evaluate("x + y") == Decimal('8')
    assert evaluator.evaluate("x * y") == Decimal('15')
    
    # Test functions
    assert evaluator.evaluate("add(1, 2)") == Decimal('3')
    assert evaluator.evaluate("multiply(2, 3)") == Decimal('6')
    
    # Test error cases
    with pytest.raises(ValueError):
        evaluator.evaluate("undefined_var + 1")  # Undefined variable
    
    with pytest.raises(ValueError):
        evaluator.evaluate("unknown_func(1, 2)")  # Unknown function
    
    with pytest.raises(ValueError):
        evaluator.evaluate("1 + ")  # Invalid syntax

def test_custom_functions():
    """Test custom function registration."""
    evaluator = ExpressionEvaluator()
    
    # Register custom function
    def custom_add(a, b):
        return a + b + 1
    
    evaluator.register_function('custom_add', custom_add)
    assert evaluator.evaluate("custom_add(1, 2)") == Decimal('4')
    
    # Test function with multiple arguments
    def custom_sum(*args):
        return sum(args)
    
    evaluator.register_function('custom_sum', custom_sum)
    assert evaluator.evaluate("custom_sum(1, 2, 3)") == Decimal('6')

def test_complex_expressions():
    """Test complex expression evaluation."""
    evaluator = ExpressionEvaluator()
    
    # Test nested function calls
    assert evaluator.evaluate("add(multiply(2, 3), 4)") == Decimal('10')
    
    # Test complex arithmetic
    assert evaluator.evaluate("(1 + 2) * (3 + 4)") == Decimal('21')
    assert evaluator.evaluate("2 ** 3 + 4 * 5") == Decimal('28')
    
    # Test with variables and functions
    evaluator.set_variable('x', 5)
    assert evaluator.evaluate("add(x, multiply(2, 3))") == Decimal('11')
    assert evaluator.evaluate("(x + 1) * (x - 1)") == Decimal('24') 