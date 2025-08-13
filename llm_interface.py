import sys
import os
import requests
from typing import Dict, Any, Optional
import time

class LLMInterface:
    """
    Interface for sending code completion requests to a Large Language Model.
    This class handles communication with the LLM API and processes responses.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat"):
        """
        Initialize the LLM interface.
        
        Args:
            api_key: API key for the LLM service, defaults to environment variable
            model: The model to use for completions
        """
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            print("Warning: No API key provided. Set DEEPSEEK_API_KEY environment variable or pass to constructor.")
        
        self.model = model
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
    
    def complete_code(self, prompt: str, max_tokens: int = 2000) -> str:
        """
        Send a code completion request to the LLM.
        
        Args:
            prompt: The prompt with debug information
            max_tokens: Maximum tokens in the response
            
        Returns:
            The LLM response
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens
        }
        
        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=data
            )
            
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])
        except Exception as e:
            print(f"Error sending request to LLM: {str(e)}")
            return str(e)
    
    def extract_code_from_response(self, response: Dict[str, Any]) -> str:
        """
        Extract code blocks from the LLM response.
        
        Args:
            response: The LLM response
            
        Returns:
            Extracted code as a string
        """
        if "error" in response:
            return f"# Error: {response['error']}"
        
        try:
            # Extract from DeepSeek response format
            if "choices" in response and len(response["choices"]) > 0:
                text = response["choices"][0]["message"]["content"]
            else:
                return "# No content found in response"
            
            # Extract code blocks (anything between ```python and ```)
            code_blocks = []
            in_code_block = False
            current_block = []
            
            for line in text.split("\n"):
                if line.strip().startswith("```python"):
                    in_code_block = True
                    continue
                elif line.strip() == "```" and in_code_block:
                    in_code_block = False
                    code_blocks.append("\n".join(current_block))
                    current_block = []
                    continue
                
                if in_code_block:
                    current_block.append(line)
            
            return "\n\n".join(code_blocks)
        except Exception as e:
            return f"# Error extracting code: {str(e)}"

def run_completion(prompt):
    llm = LLMInterface()
    response = llm.complete_code(prompt)
    return response

def main():
    """
    Send a debug-based code completion request to an LLM and display the response.
    
    Usage:
        python llm_interface.py /path/to/prompt.txt
    """
    if len(sys.argv) < 2:
        print("Usage: python llm_interface.py /path/to/prompt.txt")
        sys.exit(1)
    
    prompt_path = sys.argv[1]
    
    try:
        with open(prompt_path, 'r') as f:
            prompt = f.read()
            response = run_completion(prompt)

            output_path = os.path.join("code_completion_results", f"response_{int(time.time())}.txt")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, 'w') as f:
                f.write(response)
    
            print(f"Completed code saved to {output_path}")
    except Exception as e:
        print(f"Error reading prompt file: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
