#!/bin/bash
# Startup script for MedPulse Medical & Pharmacy Portal
PORT=${PORT:-8000}
echo "=========================================================="
echo " Starting MedPulse Medical & Clinical Pharmacy Portal"
echo " Access URL: http://localhost:$PORT"
echo "=========================================================="
python3 server.py
