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

# Load environment variables from .env file
load_dotenv()

# Add run mode check
run_mode = os.getenv("RUN_MODE", "local").lower()

try:
    AZ_VISION_ENDPOINT = os.getenv("AZ_VISION_ENDPOINT")
    AZ_RESOURCE_KEY = os.getenv("AZ_RESOURCE_KEY")
    if not AZ_VISION_ENDPOINT or not AZ_RESOURCE_KEY:
        raise KeyError("Environment variables not found")
except KeyError:
    print("Missing environment variable 'AZ_VISION_ENDPOINT' or 'AZ_RESOURCE_KEY'")
    print("Set them before running this sample.")
    exit()

# Setup client
client = ImageAnalysisClient(endpoint=AZ_VISION_ENDPOINT,
                             credential=AzureKeyCredential(AZ_RESOURCE_KEY))

def process_screenshot(file_path):
    # Extract text (OCR) from the image
    with open(file_path, "rb") as f:
        image_data = f.read()

    result = client.analyze(
        image_data=image_data,
        visual_features=[VisualFeatures.READ],
        language="en"
    )

    # Save the OCR results to a file
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    
    # Adjust output path based on run mode
    if run_mode == "docker":
        logs_dir = "/app/logs"
    else:
        logs_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    ocr_output_file = os.path.join(logs_dir, f"{timestamp}_azure_ocr_response.json")

    if result.read is not None:
        lines = ["".join(line.text) for line in result.read.blocks[0].lines]
        with open(ocr_output_file, "w") as f:
            json.dump(lines, f)

    # Adjust script path based on run mode
    current_dir = os.path.dirname(os.path.abspath(__file__))

    if run_mode == "docker":
        submit_openai_script = "/app/submit_OpenAI.py"
    else:
        submit_openai_script = os.path.join(current_dir, "submit_OpenAI.py")
        
    subprocess.run(["python3", submit_openai_script, ocr_output_file])

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python submit_Azure.py <file_path>. Resorting to use default (latest saved screenshot)")
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