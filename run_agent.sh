#!/bin/bash

# Default model, can be overridden by argument or flags
DEFAULT_MODEL="gpt-oss:20b"

# Activate venv
source venv/bin/activate

# Check if arguments were provided
if [ $# -eq 0 ]; then
    echo "Usage: ./run_agent.sh \"Your Verilog prompt\" [options]"
    echo "Example: ./run_agent.sh \"A 4-bit synchronous counter\""
    exit 1
fi

# Run the agent
# Pass all arguments to the python script

python3 src/main.py "$@" --model "$DEFAULT_MODEL"
