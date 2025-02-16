import cv2
import pytesseract
import numpy as np
from PIL import Image
import re
import os
from typing import List, Dict, Any, Optional

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

def clean_text(text: str) -> str:
    """Clean extracted text by removing straggler characters and unwanted patterns."""
    if not text:
        return ""
    
    # Split into words and clean in one pass
    cleaned_words = []
    for word in text.split():
        # Remove punctuation at word boundaries but keep internal punctuation
        word = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', word)
        
        # Keep words that:
        # 1. Have at least one alphanumeric character
        # 2. Are either longer than 1 character OR are a single alphanumeric
        # 3. Keep percentage signs and numbers with units
        if (any(c.isalnum() for c in word) and 
            (len(word) > 1 or word.isalnum()) or 
            re.match(r'^[\d.,]+%$', word) or 
            re.match(r'^[\d.,]+[kKmMbBxX]+$', word)):
            cleaned_words.append(word)
    
    return ' '.join(cleaned_words)

def preprocess_for_ocr(image: np.ndarray) -> List[np.ndarray]:
    """
    Process image in multiple ways to improve text detection for different scenarios.
    Returns a list of processed images to try OCR on.
    """
    processed_images = []
    height, width = image.shape[:2]
    
    # Original grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    processed_images.append(gray)
    
    # Inverted for light text on dark background
    inverted = cv2.bitwise_not(gray)
    processed_images.append(inverted)
    
    # Enhanced contrast using CLAHE
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    processed_images.append(enhanced)
    
    # Adaptive thresholding for better text separation
    binary_adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    processed_images.append(binary_adaptive)
    
    # Otsu's thresholding for clean black text on white
    _, binary_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    processed_images.append(binary_otsu)
    
    # Add sharpening
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(gray, -1, kernel)
    processed_images.append(sharpened)
    
    # Add denoising
    denoised = cv2.fastNlMeansDenoising(gray)
    processed_images.append(denoised)
    
    return processed_images

def merge_text_results(texts: List[str]) -> List[str]:
    """Merge multiple OCR results, removing duplicates while preserving order."""
    seen = set()
    merged = []
    for text in texts:
        lines = text.splitlines()
        for line in lines:
            cleaned = clean_text(line)
            if cleaned and cleaned not in seen and len(cleaned) > 1:  # Ignore single characters
                seen.add(cleaned)
                merged.append(cleaned)
    
    # Sort by length to prioritize longer text segments which are more likely to be meaningful
    return sorted(merged, key=len, reverse=True)

def process_image(image_path: str) -> Dict[str, Any]:
    """Process an image and return extracted text in a structured format."""
    try:
        # Read image using OpenCV
        image = cv2.imread(image_path)
        if image is None:
            return {"status": "error", "error": f"Could not read image at {image_path}"}

        # Scale image if it's too large
        max_dimension = 1920
        height, width = image.shape[:2]
        if max(height, width) > max_dimension:
            scale = max_dimension / max(height, width)
            image = cv2.resize(image, None, fx=scale, fy=scale)

        # Get multiple processed versions of the image
        processed_images = preprocess_for_ocr(image)
        
        # Extract text from each processed image
        all_texts = []
        for processed in processed_images:
            # Convert OpenCV image to PIL
            pil_image = Image.fromarray(processed)
            
            # Try different PSM modes
            psm_modes = [6, 3, 4]  # Single block, Auto, Single column
            for psm in psm_modes:
                custom_config = f'--oem 3 --psm {psm}'
                
                # Get text from image
                text = pytesseract.image_to_string(
                    pil_image,
                    config=custom_config,
                    lang='eng'
                )
                if text.strip():
                    all_texts.append(text)
        
        # Merge results and remove duplicates
        merged_lines = merge_text_results(all_texts)
        
        if merged_lines:
            return {
                "lines": merged_lines,
                "status": "success"
            }
        else:
            return {
                "status": "error",
                "error": "No text could be extracted from the image"
            }
        
    except Exception as e:
        return {
            "lines": [],
            "status": "error",
            "error": str(e)
        }