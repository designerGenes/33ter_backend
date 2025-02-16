import os
import json
import re
from typing import Dict, Any, List, Optional
from deepseek import DeepSeekAPI
from dotenv import load_dotenv

load_dotenv()

# Constants
SOLUTION_LANGUAGE = os.getenv("SOLUTION_LANGUAGE", "Swift")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_SYSTEM_MESSAGE = "You are an expert software developer who excels at solving coding challenges, and extracting the text of a coding challenge from a list of semi-related text phrases."
DEEPSEEK_PROMPT_EXTRACT="Here is a list of words which were extracted using OCR from a webpage which contained exactly 1 Leetcode-style coding challenge, and lots of other unrelated data (text from advertisements, hyperlinks, etc.) Your job is to extract the full text of the coding challenge and ONLY the coding challenge, from the list of words and phrases below. You should return the extracted challenge between the following tags: <CHALLENGE> and </CHALLENGE>."
DEEPSEEK_PROMPT_SOLVE="Afterwards, you must create a solution that solves the extracted coding challenge. You should be focused most on conciseness, efficiency, and readability, and second most on lowering time and space complexity. Do NOT include any additional functionality beyond what is required to solve the challenge. Do NOT include any comments or documentation in your solution. Ensure that your entire response is in plain text with NO markdown formatting whatsoever (do not include any markdown tags such as ```swift or ```python. You should return the challenge solution between the following tags: <SOLUTION> and </SOLUTION>. Here is the list of words and phrases extracted from the webpage: "

def extract_content_between_tags(text: str, start_tag: str, end_tag: str) -> Optional[str]:
    """Extract content between XML-style tags."""
    try:
        start_idx = text.find(start_tag)
        end_idx = text.find(end_tag)
        if (start_idx != -1 and end_idx != -1):
            content = text[start_idx + len(start_tag):end_idx].strip()
            return content
        return None
    except:
        return None

def format_code_block(code: str) -> str:
    """Format a code block with consistent indentation."""
    lines = code.split('\n')
    # Find the minimum indentation level (excluding empty lines)
    min_indent = float('inf')
    for line in lines:
        if line.strip():  # Only check non-empty lines
            indent = len(line) - len(line.lstrip())
            min_indent = min(min_indent, indent)
    
    if min_indent == float('inf'):
        min_indent = 0
        
    # Remove the common indentation
    formatted_lines = []
    for line in lines:
        if line.strip():  # Keep empty lines as is
            formatted_lines.append(line[min_indent:] if len(line) >= min_indent else line)
        else:
            formatted_lines.append('')
            
    # Ensure code block starts and ends with empty lines for better readability
    if formatted_lines and formatted_lines[0].strip():
        formatted_lines.insert(0, '')
    if formatted_lines and formatted_lines[-1].strip():
        formatted_lines.append('')
        
    return '\n'.join(formatted_lines)

async def get_completion_async(prompt: str, instructions: str, max_tokens: int = 2048, temperature: float = 0.1) -> Optional[str]:
    """Get a completion from DeepSeek API asynchronously."""
    try:
        # Mock response for now - to be replaced with actual API call
        if "coding challenge" in prompt.lower():
            return """
            Challenge:
            Given an array of integers, find the two numbers that add up to a specific target.
            Return their indices in the array.
            
            Solution:
            def find_two_sum(nums, target):
                num_dict = {}
                for i, num in enumerate(nums):
                    complement = target - num
                    if complement in num_dict:
                        return [num_dict[complement], i]
                    num_dict[num] = i
                return []
            """
        return "No coding challenge found in the provided text."
        
    except Exception as e:
        print(f"Error getting completion: {str(e)}")
        return None

async def analyze_text(extracted_text: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze text to identify coding challenges and generate solutions.
    Returns a dict with challenge description, solution, and status.
    """
    try:
        # Format the text list into a single string
        text_content = "\n".join(line["text"] for line in extracted_text)
        
        instructions = """You are a coding challenge analyzer. Examine the provided text CAREFULLY.

        What constitutes a VALID coding challenge:
        - Clear problem statements asking to implement an algorithm or function
        - Explicit programming tasks with defined inputs and outputs
        - Algorithmic problems with specific requirements
        - Coding exercises with test cases or examples
        
        What is NOT a coding challenge:
        - General documentation or API descriptions
        - Code snippets without associated problems
        - UI/UX text or application instructions
        - Error messages or logs
        - Regular technical discussions
        - Code review comments
        - Git commit messages
        - Configuration files
        
        Your task is to:
        1. ONLY identify ACTUAL coding challenges matching the above criteria
        2. If you find a legitimate coding challenge:
           - Extract and format it clearly
           - Generate an optimal solution
        3. If NO clear coding challenge exists in the text:
           - Do NOT create or imagine a challenge
           - Return status="success" with challenge=None
           - This is vital - never fabricate challenges
        4. If you're unsure if something is a coding challenge:
           - Err on the side of caution and return no challenge
           - Better to miss a challenge than create a false one

        Remember: Users are specifically looking for programming challenge problems to solve.
        Do not treat every piece of code-related text as a challenge."""

        completion = await get_completion_async(
            text_content,
            instructions,
            max_tokens=2048,
            temperature=0.1  # Keep temperature low for more conservative results
        )
        
        # Parse the completion response
        if completion and isinstance(completion, str):
            if "No coding challenge found" in completion or "No clear challenge detected" in completion:
                return {
                    "status": "success",
                    "challenge": None,
                    "solution": None
                }
            else:
                # Extract challenge and solution if present
                challenge_match = re.search(r"Challenge:(.*?)(?=Solution:|$)", completion, re.DOTALL)
                solution_match = re.search(r"Solution:(.*?)$", completion, re.DOTALL)
                
                challenge = challenge_match.group(1).strip() if challenge_match else None
                solution = solution_match.group(1).strip() if solution_match else None
                
                return {
                    "status": "success",
                    "challenge": challenge,
                    "solution": solution
                }
        else:
            return {
                "status": "error",
                "error": "Invalid response from DeepSeek"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }