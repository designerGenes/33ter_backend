import cv2
import pytesseract
import numpy as np
from PIL import Image
import io
import json
from typing import List, Dict, Any, Optional
import os

def find_tesseract_executable() -> Optional[str]:
    """Find the Tesseract executable in common installation paths."""
    possible_paths = [
        '/opt/homebrew/bin/tesseract',  # Homebrew on Apple Silicon
        '/usr/local/bin/tesseract',     # Homebrew on Intel Mac
        '/usr/bin/tesseract'            # Linux default
    ]
    
    for path in possible_paths:
        if os.path.isfile(path):
            return path
    return None

# Set Tesseract executable path
tesseract_path = find_tesseract_executable()
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    raise RuntimeError("Tesseract executable not found. Please ensure Tesseract is installed.")

def preprocess_image(image: np.ndarray) -> List[np.ndarray]:
    """
    Preprocess image for better OCR results using multiple processing methods:
    1. Original grayscale
    2. Inverted grayscale (for white on black text)
    3. Adaptive thresholding
    4. High contrast adjustment
    """
    processed_images = []
    
    # Convert to grayscale if needed
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()
    processed_images.append(gray)
    
    # Add inverted version for white text on dark background
    inverted = cv2.bitwise_not(gray)
    processed_images.append(inverted)
    
    # Add adaptive thresholded version
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    processed_images.append(binary)
    
    # Add contrast enhanced version
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    processed_images.append(enhanced)
    
    return processed_images

def is_valid_text(text_bbox: Dict[str, Any], text: str) -> bool:
    """
    Enhanced validation of detected text based on multiple criteria:
    1. Confidence score
    2. Bounding box geometry
    3. Text content characteristics
    """
    confidence = float(text_bbox.get('conf', 0))
    if confidence < 50:  # Lower threshold to catch more text
        return False
        
    # Get bounding box dimensions
    x, y, w, h = (text_bbox.get('left', 0), text_bbox.get('top', 0), 
                  text_bbox.get('width', 0), text_bbox.get('height', 0))
    
    # Skip if dimensions are invalid
    if w <= 0 or h <= 0:
        return False
    
    # Calculate aspect ratio
    aspect_ratio = w / h if h != 0 else 0
    if not (0.1 <= aspect_ratio <= 15.0):  # Relaxed aspect ratio constraints
        return False
    
    # Text content validation
    text = text.strip()
    if not text:
        return False
    
    # Skip if text is just punctuation or special characters
    if all(not c.isalnum() for c in text):
        return False
    
    return True

def merge_text_results(results: List[List[str]]) -> List[str]:
    """
    Merge text results from different processing methods,
    removing duplicates and organizing by vertical position.
    """
    # Collect all unique lines with their y-coordinates
    all_lines = {}  # y-coord -> text
    for line_group in results:
        for line in line_group:
            text = line.strip()
            if text:
                # Use the text as key to avoid duplicates
                if text not in all_lines:
                    all_lines[text] = line
    
    # Convert back to list and remove any remaining duplicates
    return list(dict.fromkeys(all_lines.values()))

def extract_text(image_path: str) -> List[str]:
    """
    Extract text from an image using multiple processing methods
    to handle different text colors and contrasts.
    """
    # Read image using OpenCV
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not read image at {image_path}")

    # Get different processed versions of the image
    processed_images = preprocess_image(image)
    
    # Extract text from each processed image
    all_results = []
    
    for processed in processed_images:
        # Convert OpenCV image to PIL Image for pytesseract
        pil_image = Image.fromarray(processed)
        
        # Configure OCR for better detection
        custom_config = r'--oem 3 --psm 6'
        
        # Get detailed OCR data
        ocr_data = pytesseract.image_to_data(pil_image, config=custom_config, 
                                           output_type=pytesseract.Output.DICT)
        
        # Extract valid text lines
        extracted_lines = []
        current_line = []
        prev_top = -1
        line_height_threshold = 5  # Reduced threshold for tighter text
        
        for i in range(len(ocr_data['text'])):
            if int(ocr_data['conf'][i]) > -1:  # Filter out non-text blocks
                text = ocr_data['text'][i].strip()
                bbox = {
                    'left': ocr_data['left'][i],
                    'top': ocr_data['top'][i],
                    'width': ocr_data['width'][i],
                    'height': ocr_data['height'][i],
                    'conf': ocr_data['conf'][i]
                }
                
                if is_valid_text(bbox, text):
                    # Check if this text belongs to a new line
                    if prev_top == -1 or abs(bbox['top'] - prev_top) > line_height_threshold:
                        if current_line:
                            extracted_lines.append(' '.join(current_line))
                            current_line = []
                        prev_top = bbox['top']
                    current_line.append(text)
        
        # Add the last line if it exists
        if current_line:
            extracted_lines.append(' '.join(current_line))
        
        all_results.append(extracted_lines)
    
    # Merge results from all processing methods
    merged_lines = merge_text_results(all_results)
    return merged_lines

def process_image(image_path: str) -> Dict[str, Any]:
    """
    Process an image and return extracted text in a structured format.
    """
    try:
        lines = extract_text(image_path)
        return {
            "lines": lines,
            "status": "success"
        }
    except Exception as e:
        return {
            "lines": [],
            "status": "error",
            "error": str(e)
        }

def process_image(image_path):
    try:
        # Read the image using OpenCV
        image = cv2.imread(image_path)
        if image is None:
            return {"status": "error", "error": f"Failed to read image: {image_path}"}

        # Convert the image to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply thresholding to get better text recognition
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Use Tesseract to do OCR on the preprocessed image
        text = pytesseract.image_to_string(binary)
        
        if not text.strip():
            # If no text was found, try again with the original grayscale image
            text = pytesseract.image_to_string(gray)

        return {"status": "success", "text": text}
    except Exception as e:
        return {"status": "error", "error": str(e)}