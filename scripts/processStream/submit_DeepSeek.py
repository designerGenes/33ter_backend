import os 
import sys
import json
from deepseek_client import analyze_text
from utils.socketio_utils import log_debug

if __name__ == "__main__":
    if len(sys.argv) != 2:
        error = "Usage: python submit_DeepSeek.py <file_path>. File should be a json file containing the extracted text from a webpage."
        log_debug(error, "DeepSeek", "error")
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
                result = analyze_text(raw_word_list)
                print(json.dumps(result))  # Print result for parent process to capture
            else:
                error = "Could not load the extracted text - empty or invalid data"
                log_debug(error, "DeepSeek", "error")
                print(json.dumps({
                    "status": "error", 
                    "error": error,
                    "challenge": None,
                    "solution": None
                }))
    except Exception as e:
        error = f"Error loading OCR results: {e}"
        log_debug(error, "DeepSeek", "error")
        print(json.dumps({
            "status": "error", 
            "error": error,
            "challenge": None,
            "solution": None
        }))
        exit(1)