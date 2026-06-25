#!/bin/bash
# Import KV-Ground-8B Q4_K_M GGUF into TrueNAS Ollama
# Run: ssh truenas.fritz.box "sudo bash /mnt/Storage/models/kv-ground/import_kv_ground.sh"
# Or copy to truenas first: scp scripts/truenas_import_kv_ground.sh truenas.fritz.box:/tmp/

set -e

GGUF_PATH="/mnt/Storage/models/kv-ground/kv-ground-8b-Q4_K_M.gguf"
OLLAMA_CONTAINER="ix-ollama-ollama-1"

echo "=== KV-Ground-8B Ollama Import ==="
echo "GGUF size: $(ls -lh "$GGUF_PATH" | awk '{print $5}')"

# 1. Create Modelfile
cat > /tmp/KV-Ground-Modelfile << 'MODELF'
FROM /root/.ollama/models/kv-ground-8b-Q4_K_M.gguf

# GUI grounding model — screenshot + element description → coordinates
TEMPLATE """{{ .Prompt }}"""

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER stop "<|im_end|>"
MODELF

# 2. Copy GGUF into Ollama container
echo "Copying GGUF to Ollama container..."
sudo docker cp "$GGUF_PATH" "${OLLAMA_CONTAINER}:/root/.ollama/models/kv-ground-8b-Q4_K_M.gguf"

# 3. Copy Modelfile into Ollama container
sudo docker cp /tmp/KV-Ground-Modelfile "${OLLAMA_CONTAINER}:/tmp/KV-Ground-Modelfile"

# 4. Create model in Ollama
echo "Creating model kv-ground-8b..."
sudo docker exec "$OLLAMA_CONTAINER" ollama create kv-ground-8b -f /tmp/KV-Ground-Modelfile

# 5. Verify
echo "Verifying..."
sudo docker exec "$OLLAMA_CONTAINER" ollama list | grep kv-ground

echo ""
echo "=== Done ==="
echo "Model: kv-ground-8b"
echo "Test:  curl http://truenas.fritz.box:30068/api/generate -d '{\"model\":\"kv-ground-8b\",\"prompt\":\"Test\"}'"
