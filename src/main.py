import typer
import yaml
import shutil
import difflib
import subprocess
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.layout import Layout
from fpdf import FPDF
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

def generate_report(output_dir: Path, metadata: dict, images: list):
    """Generates a PDF report with metadata and diagrams."""
    try:
        pdf = FPDF()
        pdf.add_page()
        
        # Title
        pdf.set_font("Helvetica", "B", 24)
        pdf.cell(0, 20, "Verilog Design Report", new_x="LMARGIN", new_y="NEXT", align="C")
        
        # Metadata
        pdf.set_font("Helvetica", "", 12)
        pdf.ln(10)
        for key, value in metadata.items():
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(40, 10, f"{key}:", border=0)
            pdf.set_font("Helvetica", "", 12)
            pdf.multi_cell(0, 10, f"{value}", new_x="LMARGIN", new_y="NEXT", align="L")
        
        # Diagrams
        for img_path, title in images:
            if img_path.exists():
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 16)
                pdf.cell(0, 15, title, new_x="LMARGIN", new_y="NEXT", align="C")
                
                # Calculate image scaling to fit page
                # A4 is 210x297mm. Margins are usually 10mm.
                # Available width ~190mm.
                pdf.image(str(img_path), w=190)
                
        report_path = output_dir / "report.pdf"
        pdf.output(report_path)
        console.print(f"[bold green]Saved Report to: File://{report_path}[/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Failed to generate PDF report: {e}[/bold red]")

def generate_diagram(verilog_file: Path, output_dir: Path) -> list:
    """Generates RTL and Gate-level block diagrams. Returns list of (path, title)."""
    images = []
    try:
        # Check availability
        subprocess.run(["yosys", "-V"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run(["dot", "-V"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        verilog_path = verilog_file.resolve()
        
        # 1. RTL Diagram (High Level)
        rtl_prefix = output_dir / "diagram_rtl"
        rtl_cmd = [
            "yosys", "-p",
            f"read_verilog {verilog_path}; hierarchy -auto-top; proc; opt; show -format dot -prefix {rtl_prefix}"
        ]
        console.print("[dim]Generating RTL diagram...[/dim]")
        subprocess.run(rtl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        
        # Convert RTL dot to PNG (better for embedding)
        rtl_dot = rtl_prefix.with_suffix(".dot")
        rtl_png = rtl_prefix.with_suffix(".png")
        if rtl_dot.exists():
            subprocess.run(["dot", "-Tpng", str(rtl_dot), "-o", str(rtl_png)], check=True)
            images.append((rtl_png, "RTL Architecture (High Level)"))
            rtl_dot.unlink()

        # 2. Gate-Level Diagram (Synthesized)
        gate_prefix = output_dir / "diagram_gate"
        gate_cmd = [
            "yosys", "-p",
            f"read_verilog {verilog_path}; hierarchy -auto-top; proc; opt; opt_clean; synth; techmap; opt_clean; show -format dot -stretch -prefix {gate_prefix}"
        ]
        console.print("[dim]Generating Gate-Level diagram...[/dim]")
        subprocess.run(gate_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)

        # Convert Gate dot to PNG
        gate_dot = gate_prefix.with_suffix(".dot")
        gate_png = gate_prefix.with_suffix(".png")
        if gate_dot.exists():
            subprocess.run(["dot", "-Tpng", str(gate_dot), "-o", str(gate_png)], check=True)
            images.append((gate_png, "Synthesized Logic (Gate Level)"))
            gate_dot.unlink()
            
    except Exception as e:
        console.print(f"[bold red]Failed to generate diagram: {e}[/bold red]")
    
    return images

def save_design(name: str, design_code: str, tb_code: str, output_dir: str, prompt: str = ""):
    """Saves successful design to the designs directory."""
    start_time = datetime.now()
    timestamp = start_time.strftime("%Y%m%d_%H%M%S")
    safe_name = name.replace(" ", "_").lower()
    save_path = Path(output_dir) / f"{timestamp}_{safe_name}"
    save_path.mkdir(parents=True, exist_ok=True)
    
    design_file = save_path / "design.v"
    with open(design_file, "w") as f:
        f.write(design_code)
    with open(save_path / "testbench.v", "w") as f:
        f.write(tb_code)
        
    console.print(f"[bold green]Saved design to: File://{save_path}[/bold green]")
    
    # Generate Diagrams
    images = generate_diagram(design_file, save_path)
    
    # Generate Report
    metadata = {
        "Prompt": prompt[:500] + "..." if len(prompt) > 500 else prompt,
        "Timestamp": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "Design Name": name,
        "Status": "Verified"
    }
    generate_report(save_path, metadata, images)

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
                save_design(name_hint, current_design, current_tb, designs_dir, prompt=active_prompt)
            break
        else:
            console.print(Panel(output, title="Simulation Failed", style="red"))
            
            if attempt < retries:
                with console.status(f"[bold orange3]Attempting fix {attempt + 1}...[/bold orange3]"):
                    # Smart Fix Heuristic
                    # 1. Compilation/Syntax Errors
                    if "syntax error" in output.lower():
                        if "generated_module_tb.v" in output or "testbench.v" in output:
                            console.print(f"[bold orange3]Testbench Syntax Error Detected - Fixing Testbench...[/bold orange3]")
                            new_tb = agent.fix_design(current_tb, output, is_testbench=True)
                            if show_diffs:
                                show_diff(current_tb, new_tb, title=f"Testbench Fixes for Attempt {attempt + 1}")
                            current_tb = new_tb
                        else:
                            console.print(f"[bold orange3]Design Syntax Error Detected - Fixing Design...[/bold orange3]")
                            new_design = agent.fix_design(current_design, output, is_testbench=False)
                            if show_diffs:
                                show_diff(current_design, new_design, title=f"Design Fixes for Attempt {attempt + 1}")
                            current_design = new_design
                    
                    # 2. Simulation/Logic Failures
                    else:
                        console.print(f"[bold orange3]Simulation Failure Detected.[/bold orange3]")
                        
                        # Heuristic: If we've failed > 2 times on logic errors, 
                        # it might be the testbench that is wrong/too strict.
                        if attempt >= 2:
                            console.print(f"[bold magenta]Persistent Failure (Attempt {attempt+1}) - Switching strategy to fix testbench...[/bold magenta]")
                            new_tb = agent.fix_design(current_tb, output, is_testbench=True)
                            if show_diffs:
                                show_diff(current_tb, new_tb, title=f"Testbench Fixes for Attempt {attempt + 1}")
                            current_tb = new_tb
                        else:
                            console.print(f"[bold orange3]Fixing Design Logic...[/bold orange3]")
                            new_design = agent.fix_design(current_design, output, is_testbench=False)
                            if show_diffs:
                                show_diff(current_design, new_design, title=f"Design Fixes for Attempt {attempt + 1}")
                            current_design = new_design
            else:
                 console.print("[bold red]Max retries reached. Validation failed.[/bold red]")

if __name__ == "__main__":
    app()
