FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

# Set up workspace first to copy requirements
WORKDIR /work

# Copy requirements
COPY requirements/requirements-rel.txt /tmp/requirements-rel.txt
COPY requirements/requirements-devtest.txt /tmp/requirements-devtest.txt
COPY tests/e2e/requirements.txt /tmp/requirements-e2e.txt

# Install all dependencies required for running the API and Tests
# opencv-python-headless added for CV analysis gate (cv-batch-analyze.py)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 libglib2.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    -r /tmp/requirements-rel.txt \
    -r /tmp/requirements-devtest.txt \
    -r /tmp/requirements-e2e.txt \
    opencv-python-headless==4.13.0.92 \
    ruff \
    mypy \
    types-requests

ENV PYTHONPATH=/work

# No entrypoint, use default bash or specify in command
CMD ["ruff", "check", "."]
