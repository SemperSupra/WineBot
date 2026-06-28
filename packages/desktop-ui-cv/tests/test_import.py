"""Verify the package imports correctly and exposes expected classes."""

from winebot_cv import __version__


class TestImports:
    def test_version(self):
        assert __version__ == "0.1.0"

    def test_detectors(self):
        from winebot_cv.detectors.engines import (
            UIDetector, ContourDetector, YOLOUIDetector,
            OmniParserDetector, ScreenParserDetector,
            WineUIDetector, VLMGroundingDetector,
        )
        assert WineUIDetector.name == "wine"
        assert ContourDetector.name == "contour"

    def test_ocr(self):
        from winebot_cv.ocr.engines import OCREngine, TesseractEngine
        assert issubclass(TesseractEngine, OCREngine)

    def test_registry(self):
        from winebot_cv.registry.model_registry import ModelRegistry
        assert ModelRegistry is not None
