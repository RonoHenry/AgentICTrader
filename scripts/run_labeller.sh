#!/bin/bash
# Run Pattern Labelling Tool
# Usage: ./scripts/run_labeller.sh

echo "Starting Pattern Labelling Tool..."
echo "UI will be available at: http://localhost:8502"
echo ""

streamlit run ml/models/pattern_detector/labeller_ui.py --server.port 8502
