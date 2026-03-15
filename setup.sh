#!/bin/bash
# Equity Research Agent — Setup Script
# Run: chmod +x setup.sh && ./setup.sh

set -e

echo "=== Equity Research Agent Setup ==="

# Create output directories
mkdir -p output/charts data/edgar data/fred

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt --break-system-packages --quiet

# Verify tools
echo ""
echo "Verifying tools..."
python tools/databento_feed.py --help > /dev/null 2>&1 && echo "  ✓ databento_feed.py" || echo "  ✗ databento_feed.py"
python tools/edgar.py --help > /dev/null 2>&1 && echo "  ✓ edgar.py" || echo "  ✗ edgar.py"
python tools/fred.py --help > /dev/null 2>&1 && echo "  ✓ fred.py" || echo "  ✗ fred.py"
python tools/charts.py --help > /dev/null 2>&1 && echo "  ✓ charts.py" || echo "  ✗ charts.py"
python tools/technicals.py --help > /dev/null 2>&1 && echo "  ✓ technicals.py" || echo "  ✗ technicals.py"
python tools/diagram.py --help > /dev/null 2>&1 && echo "  ✓ diagram.py" || echo "  ✗ diagram.py"
python tools/pdf_gen.py --help > /dev/null 2>&1 && echo "  ✓ pdf_gen.py" || echo "  ✗ pdf_gen.py"

# Check for Graphviz (required for diagram rendering)
echo ""
if command -v dot &> /dev/null; then
    echo "  ✓ graphviz (dot) installed"
else
    echo "  ✗ graphviz not found. Install:"
    echo "    macOS:  brew install graphviz"
    echo "    Linux:  apt-get install graphviz"
fi

# Check for API keys
echo ""
if [ -z "$DATABENTO_API_KEY" ]; then
    echo "  ⚠ DATABENTO_API_KEY not set. Get one at: https://databento.com/signup"
    echo "    Set it: export DATABENTO_API_KEY='your_key_here'"
else
    echo "  ✓ DATABENTO_API_KEY is set"
fi

echo ""
if [ -z "$FRED_API_KEY" ]; then
    echo "  ⚠ FRED_API_KEY not set. Get one at: https://fred.stlouisfed.org/docs/api/api_key.html"
    echo "    Set it: export FRED_API_KEY='your_key_here'"
else
    echo "  ✓ FRED_API_KEY is set"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Usage with Claude Code:"
echo '  cd equity-research-agent'
echo '  claude                              # interactive session'
echo '  claude -p "Research AAPL"           # one-shot mode'
