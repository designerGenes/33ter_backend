import os
from openai import OpenAI
import glob
from dotenv import load_dotenv
import json
import requests  # Add this import
import sys  # Add this import

load_dotenv()

# Load your API key from an environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_SYSTEM_MESSAGE = """You are a diligent and helpful software developer who excels at solving coding challenges,
and extracting the text of a coding challenge from a list of semi-related text phrases.
    """
OPENAI_PROMPT_EXTRACT = """Here is an array of words which were extracted using OCR from a webpage.
The page contained (at least) a Leetcode-style coding challenge,
and lots of other unrelated data such as text from advertisements, hyperlinks, etc.
Your job is to extract the full text of the coding challenge and ONLY the coding challenge,
from the list of words and phrases below:
"""

# Get the programming language from environment variable, default to Python
SOLUTION_LANGUAGE = os.getenv("SOLUTION_LANGUAGE", "Python")

OPENAI_PROMPT_SOLVE = f"""
Now that you have received the text of a coding challenge, create a {SOLUTION_LANGUAGE} function that solves the coding challenge below.
You should be focused most on conciseness, efficiency, and readability, and second most on lowering time and space complexity.
You should respond FIRST with your solution to the coding challenge (written in {SOLUTION_LANGUAGE}),
and then afterwards with a line-by-line explanation of your code.
    Example:
    SOLUTION
    (full {SOLUTION_LANGUAGE} solution, written to be as time and space efficient as possible)
    (two line breaks)
    EXPLANATION
    (segment 1 of the same {SOLUTION_LANGUAGE} solution)
    EXPLANATION of segment 1 in a conversational tone
    (segment 2 of the same {SOLUTION_LANGUAGE} solution, if it exists)
    EXPLANATION of segment 2 in a conversational tone

Here is the coding challenge and related details:
"""

client = OpenAI(api_key=OPENAI_API_KEY)

def submit_for_extraction(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": OPENAI_SYSTEM_MESSAGE},
                {"role": "user", "content": f"{OPENAI_PROMPT_EXTRACT}\n{prompt}"}
            ],
            max_tokens=10000,
            temperature=0.7
        )
        print("Received coding challenge response: ")
        with open('/app/logs/extracted_challenge.txt', 'w') as f:
            f.write(response.choices[0].message.content)
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in extraction: {e}")
        return None

def submit_for_code_solution(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",  # Use the correct model name
            messages=[
                {"role": "system", "content": OPENAI_SYSTEM_MESSAGE},
                {"role": "user", "content": f"{OPENAI_PROMPT_SOLVE}\n\n{prompt}"}
            ],
            max_tokens=10000,
            temperature=0.7
        )
        print("Received coding challenge SOLUTION: ")
        with open('/app/logs/solution.txt', 'w') as f:
            f.write(response.choices[0].message.content)
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in solution generation: {e}")
        return None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python submit_OpenAI.py <file_path>")
        exit(1)
    
    file_path = sys.argv[1]

    try:
        with open(file_path, "r") as f:
            raw_word_list = json.load(f)  # Assuming the JSON file contains an array of strings
            if raw_word_list is not None:
                extracted = submit_for_extraction(json.dumps(raw_word_list))
                if extracted:
                    solution = submit_for_code_solution(extracted)
                    if solution:
                        # Send the solution to the Socket.IO server (Container #2)
                        SOCKETIO_PORT = os.getenv("SOCKETIO_PORT", 5347)
                        response = requests.post(
                            f'http://publish-message:{SOCKETIO_PORT}/broadcast',  # Changed container3 to publish-message for clarity
                            json={
                                "data": {
                                    "title": "coding challenge",
                                    "message": solution
                                }
                            }
                        )
                        print(f"Socket.IO server response: {response.status_code} - {response.text}")  # Add this line
                        if response.status_code == 200:
                            print("Solution sent to Socket.IO server")
                        else:
                            print("Failed to send solution to Socket.IO server")
                    else:
                        print("Failed to generate solution")
                else:
                    print("Failed to extract challenge")
            else:
                print("Could not load the file")
        print(f"Loaded OCR data from: {file_path}")  # Corrected variable name
    except Exception as e:
        print(f"Error reading Azure OCR response file: {e}")
        raw_word_list = None