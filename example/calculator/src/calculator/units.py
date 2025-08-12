"""Unit conversion module."""

from typing import Dict, Callable, Union, Tuple
from decimal import Decimal
from .arithmetic import Number

class UnitConverter:
    """Handles unit conversions."""
    
    def __init__(self):
        self.converters: Dict[str, Dict[str, Callable[[Number], Number]]] = {}
        self._register_default_converters()
    
    def _register_default_converters(self):
        """Register default unit converters."""
        # Length conversions
        self.register_converter('length', 'm', 'cm', lambda x: x * 100)
        self.register_converter('length', 'cm', 'm', lambda x: x / 100)
        self.register_converter('length', 'm', 'km', lambda x: x / 1000)
        self.register_converter('length', 'km', 'm', lambda x: x * 1000)
        
        # Weight conversions
        self.register_converter('weight', 'kg', 'g', lambda x: x * 1000)
        self.register_converter('weight', 'g', 'kg', lambda x: x / 1000)
        self.register_converter('weight', 'kg', 'lb', lambda x: x * 2.20462)
        self.register_converter('weight', 'lb', 'kg', lambda x: x / 2.20462)
        
        # Temperature conversions
        self.register_converter('temperature', 'C', 'F', lambda x: x * 9/5 + 32)
        self.register_converter('temperature', 'F', 'C', lambda x: (x - 32) * 5/9)
        self.register_converter('temperature', 'C', 'K', lambda x: x + 273.15)
        self.register_converter('temperature', 'K', 'C', lambda x: x - 273.15)
    
    def register_converter(self, category: str, from_unit: str, to_unit: str, 
                          converter: Callable[[Number], Number]):
        """Register a new unit converter."""
        if category not in self.converters:
            self.converters[category] = {}
        
        key = f"{from_unit}->{to_unit}"
        self.converters[category][key] = converter
    
    def convert(self, value: Number, category: str, from_unit: str, to_unit: str) -> Number:
        """Convert a value from one unit to another."""
        if category not in self.converters:
            raise ValueError(f"Unknown category: {category}")
        
        if from_unit == to_unit:
            return value
        
        # Try direct conversion
        key = f"{from_unit}->{to_unit}"
        if key in self.converters[category]:
            return self.converters[category][key](value)
        
        # Try reverse conversion
        key = f"{to_unit}->{from_unit}"
        if key in self.converters[category]:
            # Find the inverse function
            converter = self.converters[category][key]
            # This is a simplification - in reality, we'd need to handle the inverse properly
            return value / converter(1)
        
        raise ValueError(f"No conversion found from {from_unit} to {to_unit} in category {category}")

def convert_units(value: Number, category: str, from_unit: str, to_unit: str) -> Number:
    """Convert a value from one unit to another using the default converter."""
    converter = UnitConverter()
    return converter.convert(value, category, from_unit, to_unit)

def get_available_units(category: str) -> Tuple[str, ...]:
    """Get all available units for a category."""
    converter = UnitConverter()
    if category not in converter.converters:
        return tuple()
    
    units = set()
    for key in converter.converters[category].keys():
        from_unit, to_unit = key.split('->')
        units.add(from_unit)
        units.add(to_unit)
    
    return tuple(sorted(units)) 