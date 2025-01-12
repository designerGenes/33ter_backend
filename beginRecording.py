import time
from io import BytesIO

import pyautogui
import requests

API_URL = "http://localhost:5346/upload"

while True:
    # Capture the screenshot
    screenshot = pyautogui.screenshot()

    # Save the screenshot to an in-memory buffer
    buffer = BytesIO()
    screenshot.save(buffer, format="PNG")
    buffer.seek(0)

    # Send the screenshot to the server
    # name the file with a precise timestamp to avoid overwriting and allow us to delete screenshots over X minutes old
    file_name = f"{int(time.time())}_capture.png"
    response = requests.post(API_URL, files={"file": (file_name, buffer)})
    print(response.text)

    # Wait before the next capture
    time.sleep(1)
