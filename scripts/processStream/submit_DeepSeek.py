from curses import raw
from math import log
import os 
from debugpy import log_to
from deepseek import DeepSeekAPI
from dotenv import load_dotenv
import json, requests, sys


MAGIC_DEFAULT_PORT=5348
SOLUTION_LANGUAGE = os.getenv("SOLUTION_LANGUAGE", "Swift")
DEEPSEEK_API_KEY=os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_CHAT_MODEL="deepseek-chat"
DEEPSEEK_BASE_URL="https://api.deepseek.com"
DEEPSEEK_SYSTEM_MESSAGE="You are an expert software developer who excels at solving coding challenges, and extracting the text of a coding challenge from a list of semi-related text phrases."
DEEPSEEK_PROMPT_EXTRACT="Here is a list of words which were extracted using OCR from a webpage which contained exactly 1 Leetcode-style coding challenge, and lots of other unrelated data (text from advertisements, hyperlinks, etc.) Your job is to extract the full text of the coding challenge and ONLY the coding challenge, from the list of words and phrases below. You should return the extracted challenge between the following tags: <CHALLENGE> and </CHALLENGE>."
DEEPSEEK_PROMPT_SOLVE="Afterwards, you must create a solution that solves the extracted coding challenge. You should be focused most on conciseness, efficiency, and readability, and second most on lowering time and space complexity. Do NOT include any additional functionality beyond what is required to solve the challenge. Do NOT include any comments or documentation in your solution. Ensure that your entire response is in plain text with NO markdown formatting whatsoever (do not include any markdown tags such as ```swift or ```python. You should return the challenge solution between the following tags: <SOLUTION> and </SOLUTION>. Here is the list of words and phrases extracted from the webpage: "

# Initialize global variables
socketIO_server_host = None
socketIO_server_port = None
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
            # max_tokens=2048,
            temperature=0.1,
            prompt=TOTAL_PROMPT,
            prompt_sys=DEEPSEEK_SYSTEM_MESSAGE,
        )
        if response is not None:
            # extract the challenge which should be between <CHALLENGE> and </CHALLENGE>
            challenge_start = response.find("<CHALLENGE>")
            challenge_end = response.find("</CHALLENGE>")
            if challenge_start != -1 and challenge_end != -1:
                challenge = response[challenge_start + len("<CHALLENGE>"):challenge_end]
                log_to_socketio(challenge, title="Challenge", logType="info")
            # extract the solution which should be between <SOLUTION> and </SOLUTION>
            solution_start = response.find("<SOLUTION>")
            solution_end = response.find("</SOLUTION>")
            if solution_start != -1 and solution_end != -1:
                solution = response[solution_start + len("<SOLUTION>"):solution_end]
                log_to_socketio(solution, title="Solution", logType="prime")
        else:
            log_to_socketio("DeepSeek API returned None", logType="error")
    except Exception as e:
        print(f"Error! Exceptions says: {e}")
        return None
    return

def discover_server_config():
    run_mode = os.getenv("RUN_MODE", "local").lower()
    server_config_path = "/app/server_config.json" if run_mode == "docker" else "server_config.json"
    default_host = "host.docker.internal" if run_mode == "docker" else "localhost"
    
    global socketIO_server_host
    global socketIO_server_port
    if socketIO_server_host is not None and socketIO_server_port is not None:
        return socketIO_server_host, socketIO_server_port
    try:
        with open(server_config_path, 'r') as f:
            config = json.load(f)
            socketIO_server_host = config.get('ip', default_host)  # Use run_mode-specific default
            socketIO_server_port = config.get('port', MAGIC_DEFAULT_PORT)
            return socketIO_server_host, socketIO_server_port
    except FileNotFoundError:
        print(f"Server config not found at {server_config_path}, using defaults")
        socketIO_server_host = default_host  # Use run_mode-specific default
        socketIO_server_port = os.getenv("SOCKETIO_PORT", MAGIC_DEFAULT_PORT)
        return socketIO_server_host, socketIO_server_port


def send_to_socketio(jsonObject, socketIO_server_host="localhost", socketIO_server_port=MAGIC_DEFAULT_PORT):
    try:
        # Add room to message structure
        if "data" in jsonObject:
            if "room" not in jsonObject:
                jsonObject["room"] = "cheddarbox_room"  # Add default room
        
        response = requests.post(
            f'http://{socketIO_server_host}:{socketIO_server_port}/broadcast',
            json=jsonObject,
            timeout=5  # Add timeout
        )
        print(f"Socket.IO server response: {response.status_code} - {response.text}")
        if response.status_code != 200:
            # print("Message successfully sent to Socket.IO server")
        # else:
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
                    "message": log_message,  # Changed from solution to log_message
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
                submit_for_code_solution(raw_word_list)
            else:
                log_to_socketio("Could not load the file containing the extracted text", logType="error")
        
    except Exception as e:
        print(f"Error! Exceptions says: {e}")
        exit(1)