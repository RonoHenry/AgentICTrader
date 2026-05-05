#!/bin/bash
# Run Edge Analysis Dashboard on port 8501

# Set default Analytics Service URL if not provided
export ANALYTICS_SERVICE_URL=${ANALYTICS_SERVICE_URL:-http://localhost:8000}

echo "Starting Edge Analysis Dashboard..."
echo "Analytics Service URL: $ANALYTICS_SERVICE_URL"
echo "Dashboard will be available at: http://localhost:8501"
echo ""

# Run Streamlit dashboard
streamlit run services/analytics/dashboard.py --server.port 8501
