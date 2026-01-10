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
    prompt: str = typer.Argument(None, help="Description of the hardware module to build"),
    model: str = typer.Option(None, help="Ollama model to use (overrides config)"),
    max_retries: int = typer.Option(None, help="Maximum self-correction attempts (overrides config)"),
    config_file: str = typer.Option("config.yaml", help="Path to configuration file")
):
    """
    Generates, stimulates, and validates a Verilog module from a text description.
    """
    # 1. Load Config
    config = load_config(config_file)
    
    # 2. Determine Prompt
    # CLI arg > Config > Error
    active_prompt = prompt or config.get("prompt")
    
    if not active_prompt:
        console.print("[bold red]Error: No prompt provided.[/bold red]")
        console.print("Please provide a prompt via CLI argument or 'prompt' field in config.yaml")
        raise typer.Exit(code=1)

    # Check if prompt is a file path
    if Path(active_prompt).is_file():
        console.print(f"[dim]Loading prompt from file: {active_prompt}[/dim]")
        with open(active_prompt, "r") as f:
            active_prompt = f.read().strip()

    # 3. Override defaults with CLI args or Config
    model_name = model or config.get("model", "qwen2.5-coder:14b")
    retries = max_retries if max_retries is not None else config.get("max_retries", 5)
    designs_dir = config.get("designs_dir", "designs")
    show_diffs = config.get("show_diffs", True)
    instructions = config.get("instructions", "")

    agent = VerilogAgent(model_name=model_name, extra_instructions=instructions)
    sim = VerilogSimulator(work_dir=config.get("workspace_dir", "build"))
    
    console.print(Panel(f"[bold blue]Goal:[/bold blue] {active_prompt}\n[dim]Model: {model_name}[/dim]", title="Verilog Agent"))

    if instructions:
        console.print(Panel(f"[dim]{instructions}[/dim]", title="Global Instructions"))

    # 4. Generate Design
    with console.status("[bold green]Generating Verilog Design...[/bold green]"):
        design_code = agent.generate_design(active_prompt)
    
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
                # Use active_prompt for the directory name, truncated and sanitized
                # active_prompt might be a file content, so we should be careful.
                # If prompt arg was None, we used config prompt.
                
                # If active_prompt implies a file path, we might want to use the filename?
                # But active_prompt was overwritten with content in step 2.
                # Let's just use a safe string or the first few chars of the content.
                
                name_hint = active_prompt[:20] if active_prompt else "generated_design"
                save_design(name_hint, current_design, current_tb, designs_dir)
            break
        else:
            console.print(Panel(output, title="Simulation Failed", style="red"))
            
            if attempt < retries:
                with console.status(f"[bold orange3]Attempting fix {attempt + 1}...[/bold orange3]"):
                    # Smart Fix Heuristic
                    # Check if error mentions the testbench file
                    if "generated_module_tb.v" in output or "testbench.v" in output:
                        console.print(f"[bold orange3]Fixing Testbench...[/bold orange3]")
                        new_tb = agent.fix_design(current_tb, output, is_testbench=True)
                        if show_diffs:
                            show_diff(current_tb, new_tb, title=f"Testbench Fixes for Attempt {attempt + 1}")
                        current_tb = new_tb
                    else:
                        console.print(f"[bold orange3]Fixing Design...[/bold orange3]")
                        # Pass explicit is_testbench=False
                        new_design = agent.fix_design(current_design, output, is_testbench=False)
                        if show_diffs:
                            show_diff(current_design, new_design, title=f"Design Fixes for Attempt {attempt + 1}")
                        current_design = new_design
            else:
                 console.print("[bold red]Max retries reached. Validation failed.[/bold red]")

if __name__ == "__main__":
    app()
