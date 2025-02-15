import os
from dotenv import load_dotenv
import datetime
import json
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential
import subprocess
import sys
import glob
from socketio_utils import log_to_socketio

load_dotenv()

run_mode = os.getenv("RUN_MODE", "local").lower()

try:
    AZ_VISION_ENDPOINT = os.getenv("AZ_VISION_ENDPOINT")
    AZ_RESOURCE_KEY = os.getenv("AZ_RESOURCE_KEY")
    if not AZ_VISION_ENDPOINT or not AZ_RESOURCE_KEY:
        raise KeyError("Environment variables not found")
except KeyError:
    log_to_socketio("Missing environment variable 'AZ_VISION_ENDPOINT' or 'AZ_RESOURCE_KEY'", "Azure Vision", "error")
    exit()

# Setup client
client = ImageAnalysisClient(endpoint=AZ_VISION_ENDPOINT,
                             credential=AzureKeyCredential(AZ_RESOURCE_KEY))

def process_screenshot(file_path):
    log_to_socketio(f"Processing screenshot: {file_path}", "Azure Vision", "info")
    
    # Extract text (OCR) from the image
    with open(file_path, "rb") as f:
        image_data = f.read()

    try:
        result = client.analyze(
            image_data=image_data,
            visual_features=[VisualFeatures.READ],
            language="en"
        )
    except Exception as e:
        error_msg = f"Error analyzing image: {str(e)}"
        log_to_socketio(error_msg, "Azure Vision", "error")
        print(json.dumps({"error": error_msg}))
        return

    # Save the OCR results to a file and also prepare output
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    
    if run_mode == "docker":
        logs_dir = "/app/logs"
    else:
        logs_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    ocr_output = None
    if result.read is not None:
        lines = ["".join(line.text) for line in result.read.blocks[0].lines]
        ocr_output = {
            "timestamp": timestamp,
            "lines": lines,
            "status": "success"
        }
        
        # Save to file
        ocr_output_file = os.path.join(logs_dir, f"{timestamp}_azure_ocr_response.json")
        with open(ocr_output_file, "w") as f:
            json.dump(ocr_output, f, indent=2)
            
        log_to_socketio("OCR completed successfully", "Azure Vision", "info")
        print(json.dumps(ocr_output))  # Print for process output capture
        
        # Call DeepSeek script
        if run_mode == "docker":
            submit_deepseek_script = "/app/submit_DeepSeek.py"
        else:
            submit_deepseek_script = os.path.join(os.path.dirname(__file__), "submit_DeepSeek.py")
        
        try:
            subprocess.run(["python3", submit_deepseek_script, ocr_output_file], check=True)
        except subprocess.CalledProcessError as e:
            error_msg = f"Error running DeepSeek analysis: {str(e)}"
            log_to_socketio(error_msg, "Azure Vision", "error")
            print(json.dumps({"error": error_msg}))
    else:
        error_msg = "No text detected in image"
        log_to_socketio(error_msg, "Azure Vision", "warning")
        print(json.dumps({"error": error_msg}))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        log_to_socketio("No file path provided, using latest screenshot", "Azure Vision", "info")
        # Adjust screenshots path based on run mode
        screenshots_dir = "/app/screenshots" if run_mode == "docker" else "./screenshots"
        list_of_files = glob.glob(os.path.join(screenshots_dir, '*.png'))
        if not list_of_files:
            print("No screenshots found in the directory.")
            exit()
        file_path = max(list_of_files, key=os.path.getctime)  # get the most recent file
    else:
        file_path = sys.argv[1]
    process_screenshot(file_path)