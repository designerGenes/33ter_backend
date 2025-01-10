import os
from dotenv import load_dotenv
import datetime
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential
from flask import Flask, request, jsonify
import subprocess

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

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

@app.route("/process", methods=["POST"])
def process_screenshot():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    # Save the file temporarily
    file_path = f"/app/screenshots/{file.filename}"
    file.save(file_path)

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
    ocr_output_file = f"/app/logs/{timestamp}_azure_oc_response.json"

    if result.read is not None:
        lines = ["".join(line.text) for line in result.read.blocks[0].lines]
        with open(ocr_output_file, "w") as f:
            json.dump(lines, f)

    # Pass the OCR output file to submitToOpenAI.py
    subprocess.run(["python3", "/app/submitToOpenAI.py", ocr_output_file])

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)