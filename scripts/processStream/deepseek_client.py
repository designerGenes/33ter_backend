import os 
from deepseek import DeepSeekAPI
from dotenv import load_dotenv
import json
from typing import Dict, Optional, Union

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
        if start_idx != -1 and end_idx != -1:
            content = text[start_idx + len(start_tag):end_idx].strip()
            return content
        return None
    except:
        return None

def analyze_text(word_list: list) -> Dict[str, Union[str, None]]:
    """Submit text to DeepSeek for analysis and return extracted challenge and solution."""
    try:
        # Initialize DeepSeek client
        deepseek_client = DeepSeekAPI(api_key=DEEPSEEK_API_KEY)
        
        # Combine extraction and solution prompts
        TOTAL_PROMPT = f'<PROMPT>{DEEPSEEK_PROMPT_EXTRACT}.  {DEEPSEEK_PROMPT_SOLVE}</PROMPT>: <WORDLIST>{word_list}</WORDLIST>'

        response = deepseek_client.chat_completion(
            temperature=0.1,
            prompt=TOTAL_PROMPT,
            prompt_sys=DEEPSEEK_SYSTEM_MESSAGE,
        )

        if response is not None:
            # Extract challenge and solution
            challenge = extract_content_between_tags(response, "<CHALLENGE>", "</CHALLENGE>")
            solution = extract_content_between_tags(response, "<SOLUTION>", "</SOLUTION>")
            
            return {
                "status": "success",
                "challenge": challenge,
                "solution": solution
            }
        else:
            return {
                "status": "error",
                "error": "DeepSeek API returned None",
                "challenge": None,
                "solution": None
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "challenge": None,
            "solution": None
        }