#!/bin/bash
echo "Building VAULT 33 Digital Edition..."
docker build -t vault33-digital .
echo "Launching invisible VAULT 33..."
docker run -it --rm -v "$(pwd)":/data vault33-digital
