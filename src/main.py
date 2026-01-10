import typer
import yaml
import shutil
import difflib
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.layout import Layout
from agent import VerilogAgent
from simulator import VerilogSimulator

app = typer.Typer()
console = Console()

def load_config(config_path: str = "config.yaml") -> dict:
    """Loads configuration from YAML file."""
    path = Path(config_path)
    if path.exists():
        with open(path, "r") as f:
            return yaml.safe_load(f)
    return {}

def save_design(name: str, design_code: str, tb_code: str, output_dir: str):
    """Saves successful design to the designs directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = name.replace(" ", "_").lower()
    save_path = Path(output_dir) / f"{timestamp}_{safe_name}"
    save_path.mkdir(parents=True, exist_ok=True)
    
    with open(save_path / "design.v", "w") as f:
        f.write(design_code)
    with open(save_path / "testbench.v", "w") as f:
        f.write(tb_code)
        
    console.print(f"[bold green]Saved design to: File://{save_path}[/bold green]")

def show_diff(old_code: str, new_code: str, title: str = "Code Changes"):
    """Displays a side-by-side or unified diff of code changes."""
    diff = difflib.unified_diff(
        old_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        fromfile="Previous",
        tofile="New",
        lineterm=""
    )
    diff_text = "".join(diff)
    if diff_text:
        console.print(Panel(Syntax(diff_text, "diff", theme="monokai"), title=title))

@app.command()
def design(
    prompt: str = typer.Argument(..., help="Description of the hardware module to build"),
    model: str = typer.Option(None, help="Ollama model to use (overrides config)"),
    max_retries: int = typer.Option(None, help="Maximum self-correction attempts (overrides config)"),
    config_file: str = typer.Option("config.yaml", help="Path to configuration file")
):
    """
    Generates, stimulates, and validates a Verilog module from a text description.
    """
    # 1. Load Config
    config = load_config(config_file)
    
    # 2. Override defaults with CLI args or Config
    model_name = model or config.get("model", "qwen2.5-coder:14b")
    retries = max_retries if max_retries is not None else config.get("max_retries", 5)
    designs_dir = config.get("designs_dir", "designs")
    show_diffs = config.get("show_diffs", True)

    agent = VerilogAgent(model_name=model_name)
    sim = VerilogSimulator(work_dir=config.get("workspace_dir", "build"))
    
    console.print(Panel(f"[bold blue]Goal:[/bold blue] {prompt}\n[dim]Model: {model_name}[/dim]", title="Verilog Agent"))

    # 3. Generate Design
    with console.status("[bold green]Generating Verilog Design...[/bold green]"):
        design_code = agent.generate_design(prompt)
    
    console.print(Panel(Syntax(design_code, "verilog", theme="monokai", line_numbers=True), title="Generated Design"))

    # 4. Generate Testbench
    with console.status("[bold green]Generating Testbench...[/bold green]"):
        tb_code = agent.generate_testbench(design_code)
    
    console.print(Panel(Syntax(tb_code, "verilog", theme="monokai", line_numbers=True), title="Generated Testbench"))

    # 5. Simulation Loop
    current_design = design_code
    current_tb = tb_code
    
    for attempt in range(retries + 1):
        console.print(f"\n[bold yellow]--- Simulation Attempt {attempt + 1} ---[/bold yellow]")
        
        success, output = sim.run_simulation(current_design, current_tb, "generated_module")
        
        if success:
            console.print(Panel(output, title="Simulation Result", style="green"))
            console.print("[bold green]SUCCESS! Design verified.[/bold green]")
            
            if config.get("save_on_success", True):
                save_design(prompt[:20], current_design, current_tb, designs_dir)
            break
        else:
            console.print(Panel(output, title="Simulation Failed", style="red"))
            
            if attempt < retries:
                with console.status(f"[bold orange3]Attempting fix {attempt + 1}...[/bold orange3]"):
                    # Determine whether verification failed or compilation failed
                    # For now, simplistic approach: fix design using error log
                    new_design = agent.fix_design(current_design, output, is_testbench=False)
                    
                    if show_diffs:
                        show_diff(current_design, new_design, title=f"Fixes for Attempt {attempt + 1}")
                    
                    current_design = new_design
            else:
                 console.print("[bold red]Max retries reached. Validation failed.[/bold red]")

if __name__ == "__main__":
    app()
