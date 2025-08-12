"""Tests for the history module."""

import pytest
import json
import os
from decimal import Decimal
from datetime import datetime
from calculator.history import History, HistoryEntry

def test_history_entry():
    """Test HistoryEntry class."""
    # Test creation
    entry = HistoryEntry("1 + 2", Decimal('3'))
    assert entry.operation == "1 + 2"
    assert entry.result == Decimal('3')
    assert isinstance(entry.timestamp, datetime)
    
    # Test with custom timestamp
    timestamp = datetime.now()
    entry = HistoryEntry("1 + 2", Decimal('3'), timestamp)
    assert entry.timestamp == timestamp
    
    # Test to_dict and from_dict
    data = entry.to_dict()
    new_entry = HistoryEntry.from_dict(data)
    assert new_entry.operation == entry.operation
    assert new_entry.result == entry.result
    assert new_entry.timestamp == entry.timestamp

def test_history_basic_operations():
    """Test basic history operations."""
    history = History(max_entries=3)
    
    # Test adding entries
    history.add_entry("1 + 2", Decimal('3'))
    history.add_entry("2 * 3", Decimal('6'))
    assert len(history.entries) == 2
    
    # Test getting entries
    entries = history.get_entries()
    assert len(entries) == 2
    assert entries[0].operation == "1 + 2"
    assert entries[1].operation == "2 * 3"
    
    # Test limit
    limited_entries = history.get_entries(limit=1)
    assert len(limited_entries) == 1
    assert limited_entries[0].operation == "2 * 3"
    
    # Test clearing
    history.clear()
    assert len(history.entries) == 0

def test_history_max_entries():
    """Test history max entries limit."""
    history = History(max_entries=2)
    
    # Add more entries than max_entries
    history.add_entry("1 + 2", Decimal('3'))
    history.add_entry("2 * 3", Decimal('6'))
    history.add_entry("3 + 4", Decimal('7'))
    
    # Check that only the most recent entries are kept
    assert len(history.entries) == 2
    assert history.entries[0].operation == "2 * 3"
    assert history.entries[1].operation == "3 + 4"

def test_history_serialization():
    """Test history serialization and deserialization."""
    history = History(max_entries=3)
    history.add_entry("1 + 2", Decimal('3'))
    history.add_entry("2 * 3", Decimal('6'))
    
    # Test to_dict and from_dict
    data = history.to_dict()
    new_history = History.from_dict(data)
    assert new_history.max_entries == history.max_entries
    assert len(new_history.entries) == len(history.entries)
    assert new_history.entries[0].operation == history.entries[0].operation
    assert new_history.entries[0].result == history.entries[0].result

def test_history_file_operations():
    """Test history file operations."""
    history = History(max_entries=3)
    history.add_entry("1 + 2", Decimal('3'))
    history.add_entry("2 * 3", Decimal('6'))
    
    # Test saving to file
    filename = "test_history.json"
    try:
        history.save_to_file(filename)
        assert os.path.exists(filename)
        
        # Test loading from file
        loaded_history = History.load_from_file(filename)
        assert loaded_history.max_entries == history.max_entries
        assert len(loaded_history.entries) == len(history.entries)
        assert loaded_history.entries[0].operation == history.entries[0].operation
        assert loaded_history.entries[0].result == history.entries[0].result
    finally:
        # Clean up
        if os.path.exists(filename):
            os.remove(filename)

def test_history_edge_cases():
    """Test history edge cases."""
    history = History(max_entries=0)
    
    # Test with max_entries = 0
    history.add_entry("1 + 2", Decimal('3'))
    assert len(history.entries) == 0
    
    # Test with empty history
    assert len(history.get_entries()) == 0
    assert len(history.get_entries(limit=1)) == 0
    
    # Test with invalid limit
    history = History(max_entries=3)
    history.add_entry("1 + 2", Decimal('3'))
    assert len(history.get_entries(limit=0)) == 0
    assert len(history.get_entries(limit=-1)) == 0 