#!/bin/bash
# Quick test runner for Slack Agent integration tests

echo "🚀 Running Slack Agent Integration Tests..."
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Run the test
python test_slack_integration.py

echo ""
echo "Test completed!"
