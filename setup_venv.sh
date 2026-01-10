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

# 2. Check for System Dependencies (Mac/Brew)
if command -v brew &> /dev/null; then
    echo "Homebrew found. Checking dependencies..."
    
    deps=("icarus-verilog" "yosys" "graphviz")
    for dep in "${deps[@]}"; do
        if ! brew list "$dep" &> /dev/null; then
            echo -e "${GREEN}Installing $dep...${NC}"
            brew install "$dep"
        else
            echo "$dep is already installed."
        fi
    done
else
    # Fallback checks
    echo -e "${RED}Warning: Homebrew not found. Skipping auto-install of system tools.${NC}"
    
    if ! command -v iverilog &> /dev/null; then
        echo -e "${RED}Error: iverilog not found. Install manually.${NC}"
    fi
     if ! command -v yosys &> /dev/null; then
        echo -e "${RED}Error: yosys not found. Install manually.${NC}"
    fi
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
