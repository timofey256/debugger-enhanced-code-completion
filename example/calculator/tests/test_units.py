"""Tests for the units module."""

import pytest
from decimal import Decimal
from calculator.units import UnitConverter, convert_units, get_available_units

def test_length_conversions():
    """Test length unit conversions."""
    # Test meters to centimeters
    assert convert_units(1, 'length', 'm', 'cm') == Decimal('100')
    assert convert_units(2.5, 'length', 'm', 'cm') == Decimal('250')
    
    # Test centimeters to meters
    assert convert_units(100, 'length', 'cm', 'm') == Decimal('1')
    assert convert_units(250, 'length', 'cm', 'm') == Decimal('2.5')
    
    # Test meters to kilometers
    assert convert_units(1000, 'length', 'm', 'km') == Decimal('1')
    assert convert_units(2500, 'length', 'm', 'km') == Decimal('2.5')
    
    # Test kilometers to meters
    assert convert_units(1, 'length', 'km', 'm') == Decimal('1000')
    assert convert_units(2.5, 'length', 'km', 'm') == Decimal('2500')

def test_weight_conversions():
    """Test weight unit conversions."""
    # Test kilograms to grams
    assert convert_units(1, 'weight', 'kg', 'g') == Decimal('1000')
    assert convert_units(2.5, 'weight', 'kg', 'g') == Decimal('2500')
    
    # Test grams to kilograms
    assert convert_units(1000, 'weight', 'g', 'kg') == Decimal('1')
    assert convert_units(2500, 'weight', 'g', 'kg') == Decimal('2.5')
    
    # Test kilograms to pounds
    assert convert_units(1, 'weight', 'kg', 'lb') == Decimal('2.20462')
    assert convert_units(2.5, 'weight', 'kg', 'lb') == Decimal('5.51155')
    
    # Test pounds to kilograms
    assert convert_units(2.20462, 'weight', 'lb', 'kg') == Decimal('1')
    assert convert_units(5.51155, 'weight', 'lb', 'kg') == Decimal('2.5')

def test_temperature_conversions():
    """Test temperature unit conversions."""
    # Test Celsius to Fahrenheit
    assert convert_units(0, 'temperature', 'C', 'F') == Decimal('32')
    assert convert_units(100, 'temperature', 'C', 'F') == Decimal('212')
    
    # Test Fahrenheit to Celsius
    assert convert_units(32, 'temperature', 'F', 'C') == Decimal('0')
    assert convert_units(212, 'temperature', 'F', 'C') == Decimal('100')
    
    # Test Celsius to Kelvin
    assert convert_units(0, 'temperature', 'C', 'K') == Decimal('273.15')
    assert convert_units(100, 'temperature', 'C', 'K') == Decimal('373.15')
    
    # Test Kelvin to Celsius
    assert convert_units(273.15, 'temperature', 'K', 'C') == Decimal('0')
    assert convert_units(373.15, 'temperature', 'K', 'C') == Decimal('100')

def test_unit_converter_class():
    """Test UnitConverter class."""
    converter = UnitConverter()
    
    # Test custom converter registration
    def custom_convert(value):
        return value * 2
    
    converter.register_converter('custom', 'a', 'b', custom_convert)
    assert converter.convert(5, 'custom', 'a', 'b') == Decimal('10')
    
    # Test error cases
    with pytest.raises(ValueError):
        converter.convert(1, 'unknown', 'm', 'cm')  # Unknown category
    
    with pytest.raises(ValueError):
        converter.convert(1, 'length', 'm', 'unknown')  # Unknown unit

def test_get_available_units():
    """Test getting available units."""
    # Test length units
    length_units = get_available_units('length')
    assert 'm' in length_units
    assert 'cm' in length_units
    assert 'km' in length_units
    
    # Test weight units
    weight_units = get_available_units('weight')
    assert 'kg' in weight_units
    assert 'g' in weight_units
    assert 'lb' in weight_units
    
    # Test temperature units
    temp_units = get_available_units('temperature')
    assert 'C' in temp_units
    assert 'F' in temp_units
    assert 'K' in temp_units
    
    # Test unknown category
    assert get_available_units('unknown') == tuple() 