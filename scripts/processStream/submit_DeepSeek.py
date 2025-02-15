from curses import raw
from math import log
import os 
from debugpy import log_to
from deepseek import DeepSeekAPI
from dotenv import load_dotenv
import json, sys
from socketio_utils import log_to_socketio

load_dotenv()
# Constants
SOLUTION_LANGUAGE = os.getenv("SOLUTION_LANGUAGE", "Swift")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_SYSTEM_MESSAGE = "You are an expert software developer who excels at solving coding challenges, and extracting the text of a coding challenge from a list of semi-related text phrases."
DEEPSEEK_PROMPT_EXTRACT="Here is a list of words which were extracted using OCR from a webpage which contained exactly 1 Leetcode-style coding challenge, and lots of other unrelated data (text from advertisements, hyperlinks, etc.) Your job is to extract the full text of the coding challenge and ONLY the coding challenge, from the list of words and phrases below. You should return the extracted challenge between the following tags: <CHALLENGE> and </CHALLENGE>."
DEEPSEEK_PROMPT_SOLVE="Afterwards, you must create a solution that solves the extracted coding challenge. You should be focused most on conciseness, efficiency, and readability, and second most on lowering time and space complexity. Do NOT include any additional functionality beyond what is required to solve the challenge. Do NOT include any comments or documentation in your solution. Ensure that your entire response is in plain text with NO markdown formatting whatsoever (do not include any markdown tags such as ```swift or ```python. You should return the challenge solution between the following tags: <SOLUTION> and </SOLUTION>. Here is the list of words and phrases extracted from the webpage: "

# Initialize deepseek client
deepseek_client = DeepSeekAPI(api_key=DEEPSEEK_API_KEY)

# Remove run_mode from global scope and move logs_dir setup into a function
def setup_logs_dir():
    run_mode = os.getenv("RUN_MODE", "local").lower()
    logs_dir = "/app/logs" if run_mode == "docker" else os.path.join(os.getcwd(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir

logs_dir = setup_logs_dir()

def submit_for_code_solution(raw_word_list):
    # we'll combine extraction and solution generation into a single prompt.  Deepseek is pretty smart
    TOTAL_PROMPT = f'<PROMPT>{DEEPSEEK_PROMPT_EXTRACT}.  {DEEPSEEK_PROMPT_SOLVE}</PROMPT>: <WORDLIST>{raw_word_list}</WORDLIST>'
    try:
        response = deepseek_client.chat_completion(
            temperature=0.1,
            prompt=TOTAL_PROMPT,
            prompt_sys=DEEPSEEK_SYSTEM_MESSAGE,
        )
        if response is not None:
            result = {
                "status": "success",
                "challenge": None,
                "solution": None
            }
            
            # extract the challenge which should be between <CHALLENGE> and </CHALLENGE>
            challenge_start = response.find("<CHALLENGE>")
            challenge_end = response.find("</CHALLENGE>")
            if challenge_start != -1 and challenge_end != -1:
                challenge = response[challenge_start + len("<CHALLENGE>"):challenge_end]
                result["challenge"] = challenge
                log_to_socketio(challenge, title="Challenge", logType="info")
            
            # extract the solution which should be between <SOLUTION> and </SOLUTION>
            solution_start = response.find("<SOLUTION>")
            solution_end = response.find("</SOLUTION>")
            if solution_start != -1 and solution_end != -1:
                solution = response[solution_start + len("<SOLUTION>"):solution_end]
                result["solution"] = solution
                log_to_socketio(solution, title="Solution", logType="prime")
            
            print(json.dumps(result, indent=2))  # Print structured output
            return result
        else:
            error = "DeepSeek API returned None"
            log_to_socketio(error, logType="error")
            print(json.dumps({"status": "error", "error": error}))
            return None
    except Exception as e:
        error = f"Error! Exception says: {e}"
        log_to_socketio(error, logType="error")
        print(json.dumps({"status": "error", "error": error}))
        return None

### main loop
if __name__ == "__main__": 
    if len(sys.argv) != 2:
        error = "Usage: python submit_DeepSeek.py <file_path>. File should be a json file containing the extracted text from a webpage."
        print(json.dumps({"status": "error", "error": error}))
        exit(1)
    
    file_path = sys.argv[1]
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            if isinstance(data, dict):
                raw_word_list = data.get("lines", [])
            else:
                raw_word_list = data  # Assume it's the direct list of strings
                
            if raw_word_list:
                log_to_socketio(f"Raw text extracted from screen: \n{raw_word_list}")
                submit_for_code_solution(raw_word_list)
            else:
                error = "Could not load the extracted text - empty or invalid data"
                log_to_socketio(error, logType="error")
                print(json.dumps({"status": "error", "error": error}))
    except Exception as e:
        error = f"Error! Exception says: {e}"
        print(json.dumps({"status": "error", "error": error}))
        exit(1)