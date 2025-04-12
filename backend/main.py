from runner import complete_function

if __name__ == "__main__":
    signature = "def add(a, b):"
    result = complete_function(
        signature=signature,
        source_path="example/target.py",
        func_name="add",
        test_path="example/test_target.py"
    )

    print("Generated code:")
    print(result)