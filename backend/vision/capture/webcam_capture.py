"""Webcam preview capture used for real-world visual questions."""
from __future__ import annotations

import base64
import io
import os
import time
import logging
import numpy as np

from PIL import Image

logger = logging.getLogger(__name__)


def is_valid_camera_feed(image: Image.Image) -> tuple[bool, str]:
    """
    Validate if the captured image shows a valid camera feed vs blank/icon screen.
    
    Returns:
        tuple[bool, str]: (is_valid, reason_if_invalid)
    """
    try:
        # Convert to numpy array for analysis
        img_array = np.array(image.convert('RGB'))
        height, width = img_array.shape[:2]
        
        # Check 1: Image too small (likely not full camera preview)
        if width < 200 or height < 150:
            return False, "Camera preview window too small"
        
        # Check 2: Calculate color variation - very low variation indicates blank/static screen
        # Convert to grayscale for easier analysis
        gray = np.mean(img_array, axis=2)
        color_std = np.std(gray)
        
        # If standard deviation is very low, it's likely a blank screen
        if color_std < 5.0:
            return False, "Camera showing blank/static screen"
        
        # Check 3: Look for common camera app UI elements that indicate no video feed
        # Check center region for solid colors (common in blank camera previews)
        center_y, center_x = height // 2, width // 2
        center_region = img_array[
            center_y - min(50, height//4) : center_y + min(50, height//4),
            center_x - min(50, width//4) : center_x + min(50, width//4)
        ]
        
        if center_region.size > 0:
            center_std = np.std(center_region)
            if center_std < 3.0:
                return False, "Camera preview showing static center (likely camera icon or blank screen)"
        
        # Check 4: Look for predominantly dark image (camera blocked/covered)
        avg_brightness = np.mean(img_array)
        if avg_brightness < 20:  # Very dark image
            return False, "Camera appears to be blocked or covered"
        
        # Check 5: Look for predominantly white/bright image (overexposed or blank)
        if avg_brightness > 240:  # Very bright/white image
            return False, "Camera showing overexposed or blank white screen"
        
        # Check 6: Color histogram analysis - real camera feeds have distributed colors
        # Flatten image and check if colors are too uniform
        flat_img = img_array.reshape(-1, 3)
        unique_colors = len(np.unique(flat_img.view(np.void), axis=0))
        total_pixels = flat_img.shape[0]
        color_diversity = unique_colors / total_pixels
        
        # If less than 1% unique colors, likely a static image
        if color_diversity < 0.01:
            return False, "Camera feed appears static (too few color variations)"
        
        # Check 7: Edge detection to see if there's meaningful content
        # Simple edge detection using standard deviation of neighboring pixels
        edges_h = np.abs(np.diff(gray, axis=1))  # horizontal edges
        edges_v = np.abs(np.diff(gray, axis=0))  # vertical edges
        edge_density = (np.sum(edges_h > 10) + np.sum(edges_v > 10)) / (width * height)
        
        # Very low edge density indicates uniform/static image
        if edge_density < 0.02:  # Less than 2% of pixels have significant edges
            return False, "Camera preview showing static screen (no meaningful content detected)"
        
        logger.info(f"Camera feed validation passed - std: {color_std:.2f}, brightness: {avg_brightness:.2f}, unique_colors: {unique_colors}, color_diversity: {color_diversity:.4f}, edge_density: {edge_density:.4f}")
        return True, "Valid camera feed detected"
        
    except Exception as e:
        logger.warning(f"Camera feed validation failed with error: {e}")
        # If validation fails, err on the side of caution
        return False, f"Camera validation error: {str(e)}"


def capture_camera_preview(timeout: float = 8.0, auto_close: bool = True) -> str:
    """
    Open/focus Windows Camera and return its visible preview as base64 JPEG.
    
    Args:
        timeout: Maximum time to wait for camera preview
        auto_close: If True, closes the camera app after capturing (default: True)
    """
    if os.name != "nt":
        return "ERROR: Camera preview is currently supported only on Windows."

    camera_was_opened_by_us = False
    try:
        from backend.tools.desktop.apps import focus_app, open_app, close_app
        import pygetwindow as gw
        
        # Check if camera is already open
        camera_already_open = False
        try:
            for window in gw.getAllWindows():
                if window.title and "camera" in window.title.lower():
                    camera_already_open = True
                    logger.info("Camera app is already open")
                    break
        except:
            pass

        # Try to focus existing camera first
        focused = focus_app("camera")
        if not str(focused).startswith("SUCCESS"):
            # Camera not open, so we need to open it
            opened = open_app("camera")
            if not str(opened).startswith("SUCCESS"):
                return f"ERROR: Could not open Camera. {opened}"
            camera_was_opened_by_us = True
            logger.info("Camera app opened by Maya")
        else:
            logger.info("Camera app focused (was already open)")

        from backend.vision.capture.screen_capture import screen_capture

        deadline = time.monotonic() + max(1.0, timeout)
        captured_image = None
        validation_error = None
        
        while time.monotonic() < deadline:
            active = gw.getActiveWindow()
            title = (getattr(active, "title", "") or "").casefold()
            if "camera" in title:
                image, _ = screen_capture.capture_as_pil()
                if image is not None:
                    # Validate if this is actually a valid camera feed
                    is_valid, validation_reason = is_valid_camera_feed(image)
                    if not is_valid:
                        logger.warning(f"Camera feed validation failed: {validation_reason}")
                        validation_error = validation_reason
                        # Continue trying for a bit in case camera is still loading
                        time.sleep(0.3)
                        continue
                    
                    # Valid image captured!
                    captured_image = image
                    break
            time.sleep(0.15)
        
        # Close camera if we opened it, or if auto_close is True
        if auto_close and (camera_was_opened_by_us or not camera_already_open):
            try:
                close_result = close_app("camera")
                logger.info(f"Camera close result: {close_result}")
                
                # Extra verification - force close if still open
                time.sleep(0.3)
                try:
                    for window in gw.getAllWindows():
                        if window.title and "camera" in window.title.lower():
                            try:
                                window.close()
                                logger.info("Force closed camera window")
                            except:
                                pass
                except:
                    pass
                    
            except Exception as e:
                logger.warning(f"Failed to close camera app: {e}")
        
        # Process result
        if captured_image is None:
            if validation_error:
                return f"ERROR: {validation_error}. Please ensure camera is working and showing live preview."
            return "ERROR: Camera opened, but a live preview could not be verified."
        
        # Resize if too large
        if captured_image.width > 1280:
            ratio = 1280 / captured_image.width
            captured_image = captured_image.resize(
                (1280, int(captured_image.height * ratio)),
                Image.Resampling.LANCZOS,
            )
        
        buffer = io.BytesIO()
        captured_image.convert("RGB").save(buffer, format="JPEG", quality=82)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        logger.info("Valid camera preview captured and encoded successfully")
        
        return f"CAMERA_PREVIEW_BASE64:{encoded}"
        
    except Exception as exc:
        logger.error(f"Could not capture Camera preview: {exc}")
        # Try to close camera on error if we opened it
        if auto_close and camera_was_opened_by_us:
            try:
                from backend.tools.desktop.apps import close_app
                close_app("camera")
                logger.info("Closed camera after error")
            except:
                pass
        return f"ERROR: Could not capture Camera preview: {exc}"
