from target import add

def test_add_positive():
    assert add(1, 2) == 3

def test_add_negative():
    print("hello")
    assert add(-1, -5) == -6

def test_add_zero():
    assert add(0, 0) == 0
