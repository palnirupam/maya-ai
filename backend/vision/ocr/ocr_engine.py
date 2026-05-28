import os
import time
import logging
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import easyocr
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

class OCREngine:
    def __init__(self):
        # Initialize easyocr lazily or upfront. Upfront is better for speed.
        self.reader = None
        self._initialize_reader()

    def _initialize_reader(self):
        try:
            logger.info("Initializing EasyOCR Model (this might take a few seconds on first run)...")
            # We use 'en' and 'bn' if needed later, just 'en' for now for speed.
            self.reader = easyocr.Reader(['en'], gpu=True)
            logger.info("EasyOCR Initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize EasyOCR: {e}")

    def preprocess_image(self, img: Image.Image) -> np.ndarray:
        """
        Preprocesses the image for better OCR accuracy.
        - Grayscale
        - Resize x2 (upscale)
        - Contrast boost
        """
        try:
            # 1. Convert to Grayscale
            img = ImageOps.grayscale(img)
            
            # 2. Resize x2 (Helps with small fonts / 1080p scaling)
            new_size = (img.width * 2, img.height * 2)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # 3. Contrast Boost
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)
            
            # Convert to numpy array for EasyOCR
            return np.array(img)
        except Exception as e:
            logger.error(f"Image preprocessing failed: {e}")
            return np.array(img) # Fallback

    def find_text_coordinates(self, image_np: np.ndarray, target_text: str, fuzzy_threshold: float = 0.70):
        """
        Scans the preprocessed image for target_text.
        Returns the center (x, y) coordinates of the best match, or None if not found.
        Note: The coordinates returned are scaled back to the ORIGINAL image size (since we resized x2).
        """
        if not self.reader:
            logger.error("EasyOCR is not initialized.")
            return None
            
        try:
            t0 = time.time()
            results = self.reader.readtext(image_np)
            t_ocr = time.time()
            logger.info(f"EasyOCR scanned image in {t_ocr - t0:.2f}s")
            
            best_match = None
            highest_score = 0.0
            best_bbox = None
            
            target_lower = target_text.lower()

            for (bbox, text, conf) in results:
                # We ignore very low confidence detections from easyocr itself
                if conf < 0.2:
                    continue
                    
                text_lower = text.lower()
                
                # Rapidfuzz partial ratio is great for finding "Search" inside "Type here to search"
                # token_set_ratio is also good.
                score = fuzz.partial_ratio(target_lower, text_lower) / 100.0
                
                if score > highest_score:
                    highest_score = score
                    best_match = text
                    best_bbox = bbox
            
            if highest_score >= fuzzy_threshold and best_bbox:
                logger.info(f"OCR Match Found: '{best_match}' (Target: '{target_text}', Score: {highest_score:.2f})")
                
                # bbox from easyocr is [ [top_left_x, top_left_y], [top_right_x, top_right_y], ... ]
                # We want the center
                top_left = best_bbox[0]
                bottom_right = best_bbox[2]
                
                center_x = (top_left[0] + bottom_right[0]) / 2.0
                center_y = (top_left[1] + bottom_right[1]) / 2.0
                
                # We must scale back by 0.5 because we upscaled the image x2 in preprocessing
                orig_x = int(center_x / 2.0)
                orig_y = int(center_y / 2.0)
                
                return (orig_x, orig_y)
            else:
                logger.info(f"No OCR match found for '{target_text}'. Best score was {highest_score:.2f} for '{best_match}'")
                return None
                
        except Exception as e:
            logger.error(f"OCR scan failed: {e}")
            return None

ocr_engine = OCREngine()
