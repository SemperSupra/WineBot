# desktop-ui-cv
"""Desktop UI element detection, OCR, state classification, and synthetic dataset generation.

Extracted from the WineBot project as a standalone package so it can be used
by WinBot, research projects, and any other desktop automation pipeline.

## Install

```bash
# From GitHub (this repo)
pip install "desktop-ui-cv[all] @ git+https://github.com/SemperSupra/WineBot.git@main#subdirectory=packages/desktop-ui-cv"

# Minimal (detection/OCR deps only, no GPU)
pip install "desktop-ui-cv[ocr] @ git+..."

# With GPU support
pip install "desktop-ui-cv[gpu,server] @ git+..."
```

## Usage

```python
from winebot_cv.detectors import WineUIDetector
from winebot_cv.ocr import PaddleOCREngine

detector = WineUIDetector()
ocr = PaddleOCREngine()

elements = detector.detect(image)
texts = ocr.detect_text(image)
```

## License

MIT
"""
