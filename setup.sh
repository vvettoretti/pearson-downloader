#!/bin/bash

# Setup script for Pearson Downloader

echo "Setting up Pearson Downloader..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3.7+ first."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Install Playwright browsers
echo "Installing Playwright browsers..."
playwright install chromium

# Create downloads directory
mkdir -p pearson_downloads

echo "Setup complete!"
echo ""
echo "To run the downloader:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Run the script: python3 main.py"
