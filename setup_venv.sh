#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Local Verilog Agent Setup...${NC}"

# 1. Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 could not be found.${NC}"
    exit 1
fi
echo "Python 3 found."

# 2. Check for Icarus Verilog
if ! command -v iverilog &> /dev/null; then
    echo -e "${RED}Warning: iverilog (Icarus Verilog) not found.${NC}"
    echo "Please install it manually. On Mac: brew install icarus-verilog"
else
    echo -e "Icarus Verilog found: $(iverilog -V | head -n 1)"
fi

# 3. Create Virtual Environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists."
fi

# 4. Activate and Install Dependencies
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}Setup Complete!${NC}"
echo "To activate the environment, run: source venv/bin/activate"
