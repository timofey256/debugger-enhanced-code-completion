"""Main calculator module."""

from typing import Dict, Any, Optional, List
from decimal import Decimal
from .arithmetic import Number, add, subtract, multiply, divide, power, sum_list, average
from .expression import ExpressionEvaluator, evaluate_expression
from .units import UnitConverter, convert_units, get_available_units
from .history import History, HistoryEntry

class Calculator:
    """Main calculator class that integrates all functionality."""
    
    def __init__(self, history_max_entries: int = 100):
        self.expression_evaluator = ExpressionEvaluator()
        self.unit_converter = UnitConverter()
        self.history = History(max_entries=history_max_entries)
        
        # Register arithmetic functions
        self.expression_evaluator.register_function('add', add)
        self.expression_evaluator.register_function('subtract', subtract)
        self.expression_evaluator.register_function('multiply', multiply)
        self.expression_evaluator.register_function('divide', divide)
        self.expression_evaluator.register_function('power', power)
        self.expression_evaluator.register_function('sum', sum_list)
        self.expression_evaluator.register_function('average', average)
    
    def evaluate(self, expression: str, variables: Optional[Dict[str, Number]] = None) -> Number:
        """Evaluate a mathematical expression."""
        if variables:
            for name, value in variables.items():
                self.expression_evaluator.set_variable(name, value)
        
        result = self.expression_evaluator.evaluate(expression)
        self.history.add_entry(expression, result)
        return result
    
    def convert(self, value: Number, category: str, from_unit: str, to_unit: str) -> Number:
        """Convert a value from one unit to another."""
        result = self.unit_converter.convert(value, category, from_unit, to_unit)
        self.history.add_entry(f"{value} {from_unit} -> {to_unit}", result)
        return result
    
    def register_function(self, name: str, func: callable) -> None:
        """Register a custom function."""
        self.expression_evaluator.register_function(name, func)
    
    def register_converter(self, category: str, from_unit: str, to_unit: str, 
                          converter: callable) -> None:
        """Register a custom unit converter."""
        self.unit_converter.register_converter(category, from_unit, to_unit, converter)
    
    def get_history(self, limit: Optional[int] = None) -> List[HistoryEntry]:
        """Get calculation history."""
        return self.history.get_entries(limit)
    
    def clear_history(self) -> None:
        """Clear calculation history."""
        self.history.clear()
    
    def save_history(self, filename: str) -> None:
        """Save calculation history to a file."""
        self.history.save_to_file(filename)
    
    def load_history(self, filename: str) -> None:
        """Load calculation history from a file."""
        self.history = History.load_from_file(filename)
    
    def get_available_units(self, category: str) -> tuple:
        """Get available units for a category."""
        return get_available_units(category)
    
    def get_variable(self, name: str) -> Number:
        """Get a variable value."""
        return self.expression_evaluator.get_variable(name)
    
    def set_variable(self, name: str, value: Number) -> None:
        """Set a variable value."""
        self.expression_evaluator.set_variable(name, value) 