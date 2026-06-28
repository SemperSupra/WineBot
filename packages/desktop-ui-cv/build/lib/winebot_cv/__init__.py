"""desktop-ui-cv: Desktop UI element detection, OCR, state classification, and synthetic dataset generation."""

__version__ = "0.1.0"

from winebot_cv.detectors.engines import (
    UIDetector, ContourDetector, YOLOUIDetector,
    OmniParserDetector, ScreenParserDetector,
    WineUIDetector, VLMGroundingDetector,
)
from winebot_cv.ocr.engines import OCREngine, TesseractEngine, PaddleOCREngine
