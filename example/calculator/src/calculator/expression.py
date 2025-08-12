"""Expression parsing and evaluation module."""

import ast
from typing import Dict, Any, Union, List
from decimal import Decimal
from .arithmetic import Number, add, subtract, multiply, divide, power

class ExpressionEvaluator:
    """Evaluates mathematical expressions."""
    
    def __init__(self):
        self.variables: Dict[str, Number] = {}
        self.functions: Dict[str, callable] = {
            'add': add,
            'subtract': subtract,
            'multiply': multiply,
            'divide': divide,
            'power': power
        }
    
    def set_variable(self, name: str, value: Number):
        """Set a variable value."""
        self.variables[name] = Decimal(str(value))
    
    def get_variable(self, name: str) -> Number:
        """Get a variable value."""
        if name not in self.variables:
            raise ValueError(f"Variable {name} not defined")
        return self.variables[name]
    
    def register_function(self, name: str, func: callable):
        """Register a custom function."""
        self.functions[name] = func
    
    def evaluate(self, expression: str) -> Number:
        """Evaluate a mathematical expression."""
        try:
            # Parse the expression into an AST
            tree = ast.parse(expression, mode='eval')
            
            # Evaluate the AST
            return self._evaluate_node(tree.body)
        except Exception as e:
            raise ValueError(f"Error evaluating expression: {str(e)}")
    
    def _evaluate_node(self, node: ast.AST) -> Number:
        """Evaluate an AST node."""
        if isinstance(node, ast.Num):
            return Decimal(str(node.n))
        elif isinstance(node, ast.Name):
            return self.get_variable(node.id)
        elif isinstance(node, ast.BinOp):
            left = self._evaluate_node(node.left)
            right = self._evaluate_node(node.right)
            
            if isinstance(node.op, ast.Add):
                return add(left, right)
            elif isinstance(node.op, ast.Sub):
                return subtract(left, right)
            elif isinstance(node.op, ast.Mult):
                return multiply(left, right)
            elif isinstance(node.op, ast.Div):
                return divide(left, right)
            elif isinstance(node.op, ast.Pow):
                return power(left, right)
            else:
                raise ValueError(f"Unsupported operator: {type(node.op)}")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Function calls must use simple names")
            
            func_name = node.func.id
            if func_name not in self.functions:
                raise ValueError(f"Unknown function: {func_name}")
            
            args = [self._evaluate_node(arg) for arg in node.args]
            return self.functions[func_name](*args)
        else:
            raise ValueError(f"Unsupported node type: {type(node)}")

def parse_expression(expression: str) -> str:
    """Parse and validate an expression string."""
    try:
        tree = ast.parse(expression, mode='eval')
        return expression
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {str(e)}")

def evaluate_expression(expression: str, variables: Dict[str, Number] = None) -> Number:
    """Evaluate an expression with optional variables."""
    evaluator = ExpressionEvaluator()
    if variables:
        for name, value in variables.items():
            evaluator.set_variable(name, value)
    return evaluator.evaluate(expression) 