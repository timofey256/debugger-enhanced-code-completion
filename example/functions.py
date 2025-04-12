from typing import List, Dict
from collections import defaultdict

def add(x: int, y: int) -> int:
    """
    Adds two integers and returns the result.
    """
    return x + y

def calculate_tax_summary(purchases: List[Dict]) -> Dict[str, Dict]:
    """
    Calculate total cost and tax per category of purchases.
    Each purchase is a dict with: 'name', 'category', 'price', 'tax_rate'
    """
    summary = defaultdict(lambda: {'total': 0.0, 'tax': 0.0})

    for item in purchases:
        category = item['category']
        price = item['price']
        tax_rate = item['tax_rate']

        tax_amount = price * tax_rate
        total_cost = price + tax_amount

        summary[category]['total'] += total_cost
        summary[category]['tax'] += tax_amount

    return dict(summary)