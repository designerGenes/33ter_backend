from curses import raw
from math import log
import os 
from debugpy import log_to
import deepseek 
from dotenv import load_dotenv
import json, requests, sys


MAGIC_DEFAULT_PORT=5347
SOLUTION_LANGUAGE = os.getenv("SOLUTION_LANGUAGE", "Swift")
DEEPSEEK_API_KEY=os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_SYSTEM_MESSAGE="""You are a diligent and helpful software developer who excels at solving coding challenges,
and extracting the text of a coding challenge from a list of semi-related text phrases."""
DEEPSEEK_PROMPT_EXTRACT="""Here is an array of words which were extracted using OCR from a webpage.
The page contained exactly one Leetcode-style coding challenge,
and lots of other unrelated data such as text from advertisements, hyperlinks, etc.
Your job is to extract the full text of the coding challenge and ONLY the coding challenge,
from the list of words and phrases below:
"""

# Get the programming language from environment variable, default to Python

DEEPSEEK_PROMPT_SOLVE=f"""
Afterwards, you must create a {SOLUTION_LANGUAGE} solution that solves the extracted coding challenge.
You should be focused most on conciseness, efficiency, and readability, and second most on lowering time and space complexity.
Do not include any additional functionality beyond what is required to solve the challenge.
Ensure that your entire response is in plain text with NO markdown formatting whatsoever (do not include any markdown tags such as ```swift or ```python.
"""

run_mode = os.getenv("RUN_MODE", "local").lower()
if run_mode == "docker":
    logs_dir = "/app/logs"
else:
    logs_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(logs_dir, exist_ok=True)

def submit_for_code_solution():
    # we'll combine extraction and solution generation into a single prompt.  Deepseek is pretty smart
    try:
        
    except Exception as e:
        print(f"Error! Exceptions says: {e}")
        return None
    return

def discover_server_config():
    server_config_path = "/app/server_config.json" if run_mode == "docker" else "server_config.json" # this could be wrong
    global socketIO_server_host
    global socketIO_server_port
    if socketIO_server_host is not None and socketIO_server_port is not None:
        return socketIO_server_host, socketIO_server_port
    try:
        with open(server_config_path, 'r') as f:
            config = json.load(f)
            socketIO_server_host = config.get('ip', 'localhost')
            socketIO_server_port = config.get('port', MAGIC_DEFAULT_PORT)
            return socketIO_server_host, socketIO_server_port
    except FileNotFoundError:
        print(f"Server config not found at {server_config_path}, using defaults")
        socketIO_server_host = "publish-message" if run_mode == "docker" else "localhost"   # this could be wrong
        socketIO_server_port = os.getenv("SOCKETIO_PORT", MAGIC_DEFAULT_PORT)
        return socketIO_server_host, socketIO_server_port


def send_to_socketio(jsonObject, socketIO_server_host="localhost", socketIO_server_port=MAGIC_DEFAULT_PORT):
    try:
        response = requests.post(
            f'http://{socketIO_server_host}:{socketIO_server_port}/broadcast',
            json=jsonObject,
            timeout=5  # Add timeout
        )
        print(f"Socket.IO server response: {response.status_code} - {response.text}")
        if response.status_code == 200:
            print("Message successfully sent to Socket.IO server")
        else:
            print(f"Failed to send solution. Status code: {response.status_code}")
    except requests.exceptions.ConnectionError as e:
        print(f"Failed to connect to Socket.IO server at {socketIO_server_host}:{socketIO_server_port}")
        print(f"Error: {e}")
    except requests.exceptions.Timeout:
        print("Request to Socket.IO server timed out")
    except Exception as e:
        print(f"Unexpected error sending solution: {e}")

def log_to_socketio(log_message, title=None, logType="info"):
    # log types: prime, info, warning, error
    # PRIME messages go to the main message output on iOS
    # all other messages go to the log output on iOS, and are not shown by default
    socketIO_server_host, socketIO_server_port = discover_server_config()
    if title is None:
        title = logType
    send_to_socketio({
                "data": {
                    "title": title,
                    "message": solution,
                    "logType": logType
                }
            },
            socketIO_server_host,
            socketIO_server_port)
    print(f"[{logType}]: \t {title}: \t {log_message}")


### main loop
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python submit_DeepSeek.py <file_path>.  File should be a json file containing the extracted text from a webpage.")
        exit(1)
    
    file_path = sys.argv[1]
    discover_server_config()
    try:
        with open(file_path, 'r') as f:
            raw_word_list = json.load(f)  # Assuming the JSON file contains an array of strings
            if raw_word_list is not None:
                log_to_socketio(f"raw text extracted from screen: \n{raw_word_list}")
                solution = submit_for_code_solution(raw_word_list)
                if solution:
                    log_to_socketio(solution, logType="prime")
                else:
                    log_to_socketio("Failed to generate solution. Deepseek is cranky.", logType="error")
            else:
                log_to_socketio("Could not load the file containing the extracted text", logType="error")
        
    except Exception as e:
        print(f"Error! Exceptions says: {e}")
        exit(1)