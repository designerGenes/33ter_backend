import os
from openai import OpenAI
import glob
from dotenv import load_dotenv
import json

load_dotenv()
# Load your API key from an environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# read the contents of the most recent azure OCR response file
try:
    # Find all files ending with "_azure_oc_response.json"
    list_of_files = glob.glob('/app/logs/*_azure_oc_response')
    if not list_of_files:
        raise FileNotFoundError("No Azure OCR response files found in /app/logs/")

    latest_file = max(list_of_files, key=os.path.getctime)
    with open(latest_file, "r") as f:
        raw_word_list = f.read()  # Assuming the JSON file contains an array of strings
    print(f"Loaded OCR data from: {latest_file}")
except Exception as e:
    print(f"Error reading Azure OCR response file: {e}")
    raw_word_list = None

OPENAI_SYSTEM_MESSAGE = """You are a diligent and helpful software developer who excels at solving coding challenges,
and extracting the text of a coding challenge from a list of semi-related text phrases.
    """
OPENAI_PROMPT_EXTRACT = """Here is an array of words which were extracted using OCR from a webpage.
The page contained (at least) a Leetcode-style coding challenge,
and lots of other unrelated data such as text from advertisements, hyperlinks, etc.
Your job is to extract the full text of the coding challenge and ONLY the coding challenge,
from the list of words and phrases below:
"""

OPENAI_PROMPT_SOLVE = """
Now that you have received the text of a coding challenge, create a Python function that solves the coding challenge below.
You should be focused most on conciseness, efficiency, and readability, and second most on lowering time and space complexity.
You should respond FIRST with your solution to the coding challenge (written in Python),
and then afterwards with a line-by-line explanation of your code.
    Example:
    SOLUTION
    (full Python solution, written to be as time and space efficient as possible)
    (two line breaks)
    EXPLANATION
    (segment 1 of the same Python solution)
    EXPLANATION of segment 1 in a conversational tone
    (segment 2 of the same Python solution, if it exists)
    EXPLANATION of segment 2 in a conversational tone

Here is the coding challenge and related details:
"""

client = OpenAI(api_key=OPENAI_API_KEY)

# now time to call our good friend Chatty McG

def submit_for_extraction(prompt):
    try:
        # Step 3: Send the prompt to the API
        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",  # Fixed model name
            messages=[
                {"role": "system", "content": OPENAI_SYSTEM_MESSAGE},
                {"role": "user", "content": f"{OPENAI_PROMPT_EXTRACT}\n{prompt}"}
            ],
            max_tokens=10000,  # Limit the response length
            temperature=0.7  # Control the randomness of the response
        )
        print("Received coding challenge response: ")
        # Save the extracted challenge to a file
        with open('/app/logs/extracted_challenge.txt', 'w') as f:
            f.write(response.choices[0].message.content)
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in extraction: {e}")
        return None

def submit_for_code_solution(prompt):
    try:
        # Step 3: Send the prompt to the API
        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",  # Fixed model name
            messages=[
                {"role": "system", "content": OPENAI_SYSTEM_MESSAGE},
                {"role": "user", "content": f"{OPENAI_PROMPT_SOLVE}\n\n{prompt}"}
            ],
            max_tokens=10000,  # Limit the response length
            temperature=0.7  # Control the randomness of the response
        )
        print("Received coding challenge SOLUTION: ")
        # Save the solution to a file
        with open('/app/logs/solution.txt', 'w') as f:
            f.write(response.choices[0].message.content)
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in solution generation: {e}")
        return None


# Step 4: Call the function

if raw_word_list is not None:
    extracted = submit_for_extraction(raw_word_list)
    if extracted:
        solution = submit_for_code_solution(extracted)
        if not solution:
            print("Failed to generate solution")
    else:
        print("Failed to extract challenge")
else:
    print("Could not load the file")