# Local Verilog Agent - User Guide

## Overview
The Local Verilog Agent is an AI-powered tool that generates, simulates, and validates Verilog hardware designs using your local Ollama LLM and Icarus Verilog.

## Setup
1.  **Prerequisites**:
    *   Python 3.8+
    *   Icarus Verilog (`brew install icarus-verilog`)
    *   Ollama (`brew install ollama`) with a model like `qwen2.5-coder:14b` or `gpt-oss:20b` pulled.
2.  **Installation**:
    ```bash
    ./setup_venv.sh
    ```

## Usage
### Quick Start
Run the helper script with your design prompt:
```bash
./run_agent.sh "A 4-bit binary up-counter with synchronous reset"
```

### CLI Options
You can also run the python script directly for more control:
```bash
source venv/bin/activate
python src/main.py "Your Prompt" [OPTIONS]
```

**Options:**
*   `--model <name>`: Specify the Ollama model (e.g., `qwen3:8b`). Overrides `config.yaml`.
*   `--max-retries <int>`: Set the maximum self-correction attempts (default: 5).
*   `--config-file <path>`: Use a custom config file (default: `config.yaml`).

## Configuration (`config.yaml`)
The agent is pre-configured via `config.yaml`. You can modify this file to change default behaviors.

```yaml
# Ollama Model Settings
model: "gpt-oss:20b"  # Default model to use

# Simulation Settings
max_retries: 5        # How many times to attempt self-correction
workspace_dir: "build" # Temporary directory for simulation files

# Output Settings
designs_dir: "designs" # Where successful designs are saved
save_on_success: true  # Set to false to disable saving
show_diffs: true       # Show colorized diffs when the agent fixes code
```

## Prompting Tips
*   **Be Specific**: "A counter" is vague. "A 4-bit synchronous up-counter with active-high reset and enable" is better.
*   **Specify Interface**: If you need specific signal names, list them (e.g., "Inputs: clk, rst, in_a; Output: out_b").
*   **Reset Logic**: Explicitly state "synchronous" or "asynchronous" and "active-high" or "active-low" to ensure the generated testbench matches the design.
