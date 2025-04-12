def complete_with_mock_llm(prompt: str) -> str:
    print("LLM received prompt:\n")
    print(prompt[:1000])
    print("\n...prompt truncated...\n")
    return """
def add(a, b):
    return a + b
"""