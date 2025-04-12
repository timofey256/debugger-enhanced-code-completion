from functions import calculate_tax_summary

def test_single_category_single_item():
    purchases = [
        {'name': 'Book', 'category': 'Education', 'price': 100.0, 'tax_rate': 0.1}
    ]
    result = calculate_tax_summary(purchases)
    assert result == {
        'Education': {'total': 110.0, 'tax': 10.0}
    }

def test_multiple_categories():
    purchases = [
        {'name': 'Book', 'category': 'Education', 'price': 100.0, 'tax_rate': 0.1},
        {'name': 'Pen', 'category': 'Stationery', 'price': 20.0, 'tax_rate': 0.05},
        {'name': 'Notebook', 'category': 'Stationery', 'price': 30.0, 'tax_rate': 0.05},
    ]
    result = calculate_tax_summary(purchases)
    assert result == {
        'Education': {'total': 110.0, 'tax': 10.0},
        'Stationery': {'total': 52.5, 'tax': 2.5}
    }

def test_zero_tax():
    purchases = [
        {'name': 'Fruit', 'category': 'Food', 'price': 50.0, 'tax_rate': 0.0}
    ]
    result = calculate_tax_summary(purchases)
    assert result == {
        'Food': {'total': 50.0, 'tax': 0.0}
    }

def test_empty_input():
    result = calculate_tax_summary([])
    assert result == {}