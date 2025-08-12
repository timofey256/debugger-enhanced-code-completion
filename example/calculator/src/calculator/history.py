"""History tracking module."""

from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from .arithmetic import Number

class HistoryEntry:
    """Represents a single history entry."""
    
    def __init__(self, operation: str, result: Number, timestamp: Optional[datetime] = None):
        self.operation = operation
        self.result = result
        self.timestamp = timestamp or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entry to dictionary."""
        return {
            'operation': self.operation,
            'result': str(self.result),
            'timestamp': self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HistoryEntry':
        """Create entry from dictionary."""
        return cls(
            operation=data['operation'],
            result=Decimal(data['result']),
            timestamp=datetime.fromisoformat(data['timestamp'])
        )

class History:
    """Tracks calculation history."""
    
    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self.entries: List[HistoryEntry] = []
    
    def add_entry(self, operation: str, result: Number) -> None:
        """Add a new history entry."""
        entry = HistoryEntry(operation, result)
        self.entries.append(entry)
        
        # Trim history if it exceeds max_entries
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
    
    def get_entries(self, limit: Optional[int] = None) -> List[HistoryEntry]:
        """Get history entries, optionally limited to the most recent ones."""
        if limit is None:
            return self.entries.copy()
        return self.entries[-limit:]
    
    def clear(self) -> None:
        """Clear all history entries."""
        self.entries.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert history to dictionary."""
        return {
            'max_entries': self.max_entries,
            'entries': [entry.to_dict() for entry in self.entries]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'History':
        """Create history from dictionary."""
        history = cls(max_entries=data['max_entries'])
        history.entries = [HistoryEntry.from_dict(entry) for entry in data['entries']]
        return history
    
    def save_to_file(self, filename: str) -> None:
        """Save history to a file."""
        import json
        with open(filename, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load_from_file(cls, filename: str) -> 'History':
        """Load history from a file."""
        import json
        with open(filename, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data) 