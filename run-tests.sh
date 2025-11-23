#!/bin/bash
# Bash script to run tests for WS Slack Translator

echo "=== WS Slack Translator Test Runner ==="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/upgrade test dependencies
echo ""
echo "Installing test dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements-test.txt

# Run tests
echo ""
echo "Running test suite..."
echo ""

python -m pytest test_http_server.py -v --tb=short --color=yes

exitCode=$?

echo ""
if [ $exitCode -eq 0 ]; then
    echo "✓ All tests passed!"
else
    echo "✗ Some tests failed"
fi

echo ""
echo "To run tests with coverage report:"
echo "  pytest test_http_server.py --cov=http_server --cov-report=html"
echo ""
echo "To run specific test class:"
echo "  pytest test_http_server.py::TestConfiguration -v"
echo ""

exit $exitCode
