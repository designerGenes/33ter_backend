import os
from dotenv import load_dotenv
import glob
import datetime
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential

# this script
# 1. selects the MOST RECENT image from inside the /app/screenshots folder,
# 2. submits this via CURL to the Azure Cognitive Services Image Analysis API version 4.0.
#   Note that for this we have an API resource key of 2ymmwUf0f4NlGLOex8wI18qRULEkXOqa2dDiZpd2VAC1DYk5j8qjJQQJ99BAACYeBjFXJ3w3AAAFACOGleNX
#   and a Vision endpoint of https://chatterboxreader.cognitiveservices.azure.com/

# Load environment variables from .env file
load_dotenv()

try:
    AZ_VISION_ENDPOINT = os.getenv("AZ_VISION_ENDPOINT")
    AZ_RESOURCE_KEY = os.getenv("AZ_RESOURCE_KEY")
    if not AZ_VISION_ENDPOINT or not AZ_RESOURCE_KEY:
        raise KeyError("Environment variables not found")
except KeyError:
    print("Missing environment variable 'AZ_VISION_ENDPOINT' or 'AZ_RESOURCE_KEY'")
    print("Set them before running this sample.")
    exit()

# setup client
client = ImageAnalysisClient(endpoint=AZ_VISION_ENDPOINT,
                             credential=AzureKeyCredential(AZ_RESOURCE_KEY))

# The response will be in JSON, and should be
# 1. saved to a file in the /app/logs folder of our container, named with a precise timestamp of the response date/time, and "azure_oc_response"


# select the most recent image from the /app/screenshots folder
list_of_files = glob.glob('/app/screenshots/*')
latest_file = max(list_of_files, key=os.path.getctime)
# Load image to analyze into a 'bytes' object
with open(latest_file, "rb") as f:
    image_data = f.read()

# Extract text (OCR) from an image stream. This will be a synchronously (blocking) call.
result = client.analyze(
    image_data=image_data,
    visual_features=[VisualFeatures.READ],
    language="en"
)

# Print text (OCR) analysis results to the console
print("Image analysis results:")
print(" Read:")
if result.read is not None:
    lines = ["".join(line.text) for line in result.read.blocks[0].lines]
    print(lines)

# save the response to a file in the /app/logs folder of our container, named with a precise timestamp of the response date/time, and "azure_oc_response"
timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

with open(f"/app/logs/{timestamp}_azure_oc_response", "w") as f:
    f.write(str(lines))
    f.close()