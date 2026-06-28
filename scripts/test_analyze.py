#!/usr/bin/env python3
"""Test the /analyze endpoint with a real frame."""
import io

import cv2
import requests

img = cv2.imread('/tmp/real-val-frames/frame_001.png')
_, buf = cv2.imencode('.png', img)
r = requests.post('http://localhost:8001/analyze',
                  files={'image': ('f.png', io.BytesIO(buf.tobytes()), 'image/png')},
                  timeout=10)
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'Elements: {len(data.get("elements", []))}')
    for e in data.get("elements", [])[:5]:
        print(f'  {e.get("type")}: {e.get("bbox")}')
else:
    print(f'Error: {r.text[:500]}')
