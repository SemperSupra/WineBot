#!/usr/bin/env python3
"""Test detection on a real demo frame."""
import requests, json, cv2

# Test with analyze endpoint (reads from disk)
r = requests.post('http://localhost:8001/analyze',
    json={'image_path': '/tmp/real-val-frames/frame_015.png',
          'ui_detector': 'wine'},
    timeout=10)
data = r.json()
print(f'Analyze status: {r.status_code}')
print(f'Elements: {len(data.get("elements", []))}')
print(f'OCR texts: {len(data.get("ocr_results", []))}')
for e in data.get("elements", [])[:5]:
    print(f'  {e.get("type")} conf={e.get("confidence",0):.2f}')

# Also try with lower confidence
r2 = requests.post('http://localhost:8001/analyze',
    json={'image_path': '/tmp/real-val-frames/frame_015.png',
          'ui_detector': 'yolo'},
    timeout=10)
data2 = r2.json()
print(f'\nYOLO (default) elements: {len(data2.get("elements", []))}')
for e in data2.get("elements", [])[:5]:
    print(f'  {e.get("type")} conf={e.get("confidence",0):.2f}')

# Check image stats
img = cv2.imread('/tmp/real-val-frames/frame_015.png')
print(f'\nImage: {img.shape} mean={img.mean():.0f} std={img.std():.0f}')
