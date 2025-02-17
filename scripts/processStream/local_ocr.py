import cv2
import pytesseract
import numpy as np
from PIL import Image
import re
import os
from typing import List, Dict, Any, Optional
import json
import time
from concurrent.futures import ThreadPoolExecutor
import asyncio
from utils.socketio_utils import log_debug

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
if (tesseract_path):
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
    
    return ' ' .join(cleaned_words)

def ensure_file_readable(file_path: str, max_retries: int = 3, retry_delay: float = 0.5) -> bool:
    """Ensure the file exists and is readable."""
    for attempt in range(max_retries):
        if not os.path.exists(file_path):
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return False
            
        try:
            # Try to get file size
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False
                
            # Try to verify PNG file integrity
            if file_path.lower().endswith('.png'):
                with open(file_path, 'rb') as f:
                    # Check PNG signature
                    png_signature = b'\x89PNG\r\n\x1a\n'
                    file_signature = f.read(8)
                    if file_signature != png_signature:
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        return False
                    
                    # Try to read the rest of the file to ensure it's not truncated
                    try:
                        f.seek(0)
                        f.read()
                    except:
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        return False
            
            return True
            
        except (IOError, OSError):
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return False
    return False

def preprocess_for_ocr(image: np.ndarray) -> List[np.ndarray]:
    """Preprocess image using various techniques to improve OCR accuracy"""
    processed_images = []
    
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    processed_images.append(gray)
    
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

def print_extracted_text(lines: List[str]):
    """Print extracted text in a formatted, themed way."""
    print("\n" + "="*50)
    print("          EXTRACTED TEXT OUTPUT")
    print("="*50 + "\n")
    
    if not lines:
        print("No text was extracted from the image.")
        return
    
    # Group lines by probable sections (e.g. longer lines might be paragraph text)
    current_section = []
    sections = []
    
    for line in lines:
        if len(line.strip()) < 3:  # Empty or very short lines mark section boundaries
            if current_section:
                sections.append(current_section)
                current_section = []
            continue
        current_section.append(line)
    
    if current_section:  # Add last section if exists
        sections.append(current_section)
    
    # Print sections with separation
    for i, section in enumerate(sections):
        if i > 0:
            print("\n" + "-"*30 + "\n")  # Section separator
        
        for line in section:
            print(f"  {line}")
    
    print("\n" + "="*50 + "\n")

def process_image(image_path: str, max_retries: int = 3) -> Dict:
    """Process an image using OpenCV and Tesseract OCR with retry logic"""
    for attempt in range(max_retries):
        try:
            if not ensure_file_readable(image_path):
                error_msg = f"File not readable after {max_retries} attempts: {image_path}"
                log_debug(error_msg, "OCR", "error")
                return {"status": "error", "error": error_msg}
            
            log_debug("Reading image file...", "OCR", "info")
            # Read image with error handling
            image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
            if image is None:
                if attempt < max_retries - 1:
                    log_debug(f"Failed to read image (attempt {attempt + 1}/{max_retries}), retrying...", "OCR", "warning")
                    time.sleep(0.5)
                    continue
                error_msg = f"Could not read image after {max_retries} attempts: {image_path}"
                log_debug(error_msg, "OCR", "error")
                return {"status": "error", "error": error_msg}

            # Get image dimensions
            height, width = image.shape[:2]

            # Verify image data
            if image.size == 0 or len(image.shape) < 2:
                if attempt < max_retries - 1:
                    log_debug(f"Invalid image data (attempt {attempt + 1}/{max_retries}), retrying...", "OCR", "warning")
                    time.sleep(0.5)
                    continue
                error_msg = "Invalid image data"
                log_debug(error_msg, "OCR", "error")
                return {"status": "error", "error": error_msg}

            log_debug("Preprocessing image for OCR...", "OCR", "info")
            # Get preprocessed versions
            processed_images = preprocess_for_ocr(image)
            
            all_text = []
            all_boxes = []
            
            log_debug("Running OCR on processed images...", "OCR", "info")
            for i, img in enumerate(processed_images, 1):
                try:
                    # Get both text and bounding boxes
                    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                    for j in range(len(data['text'])):
                        if int(data['conf'][j]) > 0:  # Filter out low confidence results
                            text = data['text'][j].strip()
                            if text:
                                x = int(data['left'][j])
                                y = int(data['top'][j])
                                w = int(data['width'][j])
                                h = int(data['height'][j])
                                all_text.append(text)
                                all_boxes.append([x, y, x + w, y + h])
                                
                    log_debug(f"OCR pass {i}/{len(processed_images)} successful", "OCR", "info")
                except Exception as e:
                    log_debug(f"OCR error on image {i}/{len(processed_images)}: {str(e)}", "OCR", "warning")
                    continue

            # Combine text and boxes, removing duplicates
            text_with_boxes = []
            seen = set()
            for text, box in zip(all_text, all_boxes):
                if text not in seen:
                    text_with_boxes.append({
                        "text": text,
                        "bbox": box
                    })
                    seen.add(text)
            
            if not text_with_boxes:
                log_debug("No text detected in image", "OCR", "warning")
                return {"status": "error", "error": "No text detected"}

            log_debug(f"Successfully extracted {len(text_with_boxes)} lines of text", "OCR", "info")

            return {
                "status": "success",
                "lines": text_with_boxes,
                "image_width": width,
                "image_height": height
            }

        except cv2.error as e:
            if "libpng error" in str(e) and attempt < max_retries - 1:
                log_debug(f"PNG read error (attempt {attempt + 1}/{max_retries}), retrying...", "OCR", "warning")
                time.sleep(0.5)
                continue
            error_msg = f"OpenCV error: {str(e)}"
            log_debug(error_msg, "OCR", "error")
            return {"status": "error", "error": error_msg}
        except Exception as e:
            error_msg = f"Error processing image: {str(e)}"
            log_debug(error_msg, "OCR", "error")
            return {"status": "error", "error": error_msg}
            
    return {"status": "error", "error": "Maximum retries exceeded"}

# Create a thread pool for CPU-intensive operations
ocr_thread_pool = ThreadPoolExecutor(max_workers=2)

async def process_image_async(image_path: str, max_retries: int = 3) -> Dict:
    """Async version of process_image that runs CPU-intensive operations in a thread pool"""
    loop = asyncio.get_event_loop()
    
    async def run_ocr_step(img):
        return await loop.run_in_executor(ocr_thread_pool, pytesseract.image_to_data, img, pytesseract.Output.DICT)
    
    async def read_and_process_image():
        if not await loop.run_in_executor(ocr_thread_pool, ensure_file_readable, image_path):
            error_msg = f"File not readable after {max_retries} attempts: {image_path}"
            log_debug(error_msg, "OCR", "error")
            return {"status": "error", "error": error_msg}
        
        log_debug("Reading image file...", "OCR", "info")
        image = await loop.run_in_executor(ocr_thread_pool, cv2.imread, image_path, cv2.IMREAD_UNCHANGED)
        
        if image is None:
            error_msg = f"Could not read image: {image_path}"
            log_debug(error_msg, "OCR", "error")
            return {"status": "error", "error": error_msg}
            
        height, width = image.shape[:2]
        
        log_debug("Preprocessing image for OCR...", "OCR", "info")
        processed_images = await loop.run_in_executor(ocr_thread_pool, preprocess_for_ocr, image)
        
        all_text = []
        all_boxes = []
        
        log_debug("Running OCR on processed images...", "OCR", "info")
        for i, img in enumerate(processed_images, 1):
            try:
                data = await run_ocr_step(img)
                for j in range(len(data['text'])):
                    if int(data['conf'][j]) > 0:
                        text = data['text'][j].strip()
                        if text:
                            x = int(data['left'][j])
                            y = int(data['top'][j])
                            w = int(data['width'][j])
                            h = int(data['height'][j])
                            all_text.append(text)
                            all_boxes.append([x, y, x + w, y + h])
                log_debug(f"OCR pass {i}/{len(processed_images)} successful", "OCR", "info")
            except Exception as e:
                log_debug(f"OCR error on image {i}/{len(processed_images)}: {str(e)}", "OCR", "warning")
                continue
        
        text_with_boxes = []
        seen = set()
        for text, box in zip(all_text, all_boxes):
            if text not in seen:
                text_with_boxes.append({
                    "text": text,
                    "bbox": box
                })
                seen.add(text)
        
        if not text_with_boxes:
            log_debug("No text detected in image", "OCR", "warning")
            return {"status": "error", "error": "No text detected"}
            
        log_debug(f"Successfully extracted {len(text_with_boxes)} lines of text", "OCR", "info")
        
        return {
            "status": "success",
            "lines": text_with_boxes,
            "image_width": width,
            "image_height": height
        }
    
    for attempt in range(max_retries):
        try:
            return await read_and_process_image()
        except Exception as e:
            if attempt < max_retries - 1:
                log_debug(f"Processing failed (attempt {attempt + 1}/{max_retries}), retrying...", "OCR", "warning")
                await asyncio.sleep(0.5)
                continue
            error_msg = f"Error processing image: {str(e)}"
            log_debug(error_msg, "OCR", "error")
            return {"status": "error", "error": error_msg}
    
    return {"status": "error", "error": "Maximum retries exceeded"}