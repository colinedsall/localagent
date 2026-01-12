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


def run_simulation_loop(sim, agent, design_code: str, tb_code: str, retries: int, show_diffs: bool, context_code: str = "") -> tuple[bool, str, str]:
    """Runs the fix loop for a single module (or top level)."""
    current_design = design_code
    current_tb = tb_code
    
    # When simulating, we must include the context (dependencies) if provided.
    # We don't fix the context, just the current design.
    
    for attempt in range(retries + 1):
        console.print(f"\n[bold yellow]--- Simulation Attempt {attempt + 1} ---[/bold yellow]")
        
        # Combine context (dependencies) + current design for simulation
        full_source = context_code + "\n" + current_design 
        success, output = sim.run_simulation(full_source, current_tb, "generated_module")
        
        if success:
            console.print(Panel(output, title="Simulation Result", style="green"))
            console.print("[bold green]SUCCESS! Module verified.[/bold green]")
            return True, current_design, current_tb
        
        else:
            console.print(Panel(output, title="Simulation Failed", style="red"))
            


            if attempt < retries:
                try:
                    with console.status(f"[bold orange3]Attempting fix {attempt + 1}...[/bold orange3]"):
                        # 1. Compilation/Syntax Errors
                        if "COMPILATION ERROR" in output or "syntax error" in output.lower():
                            if "generated_module_tb.v" in output or "testbench.v" in output:
                                console.print(f"[bold orange3]Testbench Compilation/Syntax Error - Fixing Testbench...[/bold orange3]")
                                new_tb = agent.fix_design(current_tb, output, is_testbench=True)
                                if show_diffs:
                                    show_diff(current_tb, new_tb, title=f"Testbench Fixes for Attempt {attempt + 1}")
                                current_tb = new_tb
                            else:
                                console.print(f"[bold orange3]Design Compilation/Syntax Error - Fixing Design...[/bold orange3]")
                                new_design = agent.fix_design(current_design, output, is_testbench=False)
                                if show_diffs:
                                    show_diff(current_design, new_design, title=f"Design Fixes for Attempt {attempt + 1}")
                                current_design = new_design
                        
                        # 2. Simulation/Logic Failures
                        else:
                            console.print(f"[bold orange3]Simulation Failure Detected.[/bold orange3]")
                            if attempt >= 2:
                                console.print(f"[bold magenta]Persistent Failure - Switching strategy to fix testbench...[/bold magenta]")
                                new_tb = agent.fix_testbench_logic(current_tb, current_design, output)
                                if show_diffs:
                                    show_diff(current_tb, new_tb, title=f"Testbench Fixes for Attempt {attempt + 1}")
                                current_tb = new_tb
                            else:
                                console.print(f"[bold orange3]Fixing Design Logic...[/bold orange3]")
                                new_design = agent.fix_design(current_design, output, is_testbench=False)
                                if show_diffs:
                                    show_diff(current_design, new_design, title=f"Design Fixes for Attempt {attempt + 1}")
                                current_design = new_design

                except KeyboardInterrupt:
                    console.print(f"\n[bold cyan]--- MANUAL INTERRUPT DETECTED ---[/bold cyan]")
                    console.print("You may manually edit 'build/generated_module.v' or 'build/generated_module_tb.v' now.")
                    user_choice = typer.prompt("Press [Enter] to reload files & retry, or type 'q' to quit", default="")
                    if user_choice.lower() == 'q':
                        raise typer.Exit()
                    
                    # Reload files
                    try:
                        with open("build/generated_module.v", "r") as f:
                            current_design = f.read()
                        with open("build/generated_module_tb.v", "r") as f:
                            current_tb = f.read()
                        console.print("[green]Files reloaded. Retrying simulation...[/green]")
                        continue 
                    except Exception as e:
                        console.print(f"[red]Failed to reload files: {e}[/red]")
            else:
                 console.print("[bold red]Max retries reached. Validation failed.[/bold red]")
                 return False, current_design, current_tb
                 
    return False, current_design, current_tb

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
    active_prompt = prompt or config.get("prompt")
    
    if not active_prompt:
        console.print("[bold red]Error: No prompt provided.[/bold red]")
        raise typer.Exit(code=1)

    if Path(active_prompt).is_file():
        with open(active_prompt, "r") as f:
            active_prompt = f.read().strip()

    # Setup
    # Priority: CLI > Config['llm'][provider]['model'] > Config['model'] > Default
    model_name = model
    if not model_name:
        if config.get("llm"):
             prov = config["llm"].get("provider", "ollama")
             if prov in config["llm"] and isinstance(config["llm"][prov], dict):
                 model_name = config["llm"][prov].get("model")
             else:
                 model_name = config["llm"].get("model")
        
    if not model_name:
         # Legacy config check: Ignore gpt-oss:20b
         candidate = config.get("model")
         if candidate and candidate != "gpt-oss:20b":
             model_name = candidate
         else:
             model_name = "qwen2.5-coder:14b"
    retries = max_retries if max_retries is not None else config.get("max_retries", 15)
    designs_dir = config.get("designs_dir", "designs")
    show_diffs = config.get("show_diffs", True)
    instructions = config.get("instructions", "")

    agent = VerilogAgent(model_name=model_name, extra_instructions=instructions, config=config)
    sim = VerilogSimulator(work_dir=config.get("workspace_dir", "build"))
    
    console.print(Panel(f"[bold blue]Goal:[/bold blue] {active_prompt}\n[dim]Model: {model_name}[/dim]", title="Verilog Agent"))

    # STEP 1: PLAN
    with console.status("[bold cyan]Analyzing Architecture & Planning submodules...[/bold cyan]"):
        plan = agent.generate_plan(active_prompt)
    
    console.print(f"[bold cyan]Implementation Plan:[/bold cyan]")
    for item in plan:
        console.print(f"- [bold]{item['name']}[/bold] ({item['type']}): {item['description']}")

    # STEP 2: BUILD SUBMODULES
    verified_modules_code = ""
    
    # Sort plan so submodules come first
    submodules = [p for p in plan if p['type'] != 'top']
    top_module = next((p for p in plan if p['type'] == 'top'), None)
    
    if not top_module and submodules:
         # Fallback if AI didn't label top correct
         top_module = submodules[-1]
         submodules = submodules[:-1]
    
    if not top_module and not submodules:
        # Fallback if plan failed entirely
        top_module = {'name': 'design', 'description': active_prompt}
    
    # Build Submodules
    for module in submodules:
        console.print(Panel(f"Building Submodule: {module['name']}", style="blue"))
        
        # Generator
        with console.status(f"Generating {module['name']}..."):
            # Submodules generally don't need context of other submodules unless specified, 
            # but passing strictly previously verified code helps if they are interdependent.
            sub_code = agent.generate_design(module['description'], context=verified_modules_code)
            sub_tb = agent.generate_testbench(sub_code)
        
        # Verify
        success, fixed_code, fixed_tb = run_simulation_loop(sim, agent, sub_code, sub_tb, retries, show_diffs, context_code=verified_modules_code)
        
        if success:
            verified_modules_code += f"\n// --- {module['name']} ---\n{fixed_code}\n"
            
            # SAVE SUBMODULE TO DISK
            sub_file = config.get("workspace_dir", "build") + f"/{module['name']}.v"
            with open(sub_file, "w") as f:
                f.write(fixed_code)
            console.print(f"[dim]Saved submodule to {sub_file}[/dim]")
            
        else:
            console.print(f"[bold red]Submodule {module['name']} Failed! Continuing carefully...[/bold red]")
            # We add it anyway, or else Top will fail definition. 
            # Ideally we might stop here, but let's try to proceed.
            verified_modules_code += f"\n{fixed_code}\n"

    # STEP 3: BUILD TOP LEVEL
    console.print(Panel(f"Building Top Level: {top_module['name'] or 'Top'}", style="bold blue"))
    
    with console.status("Generating Top Level Module..."):
        # Top level needs ALL previous modules as context
        top_code = agent.generate_design(active_prompt, context=verified_modules_code)
        top_tb = agent.generate_testbench(top_code)
    
    # Verify Top Level
    # Note: We pass verified_modules_code as context so simulation includes them
    success, fixed_top, fixed_top_tb = run_simulation_loop(sim, agent, top_code, top_tb, retries, show_diffs, context_code=verified_modules_code)
    
    # Save Final Artifact
    full_design = verified_modules_code + "\n" + fixed_top
    
    if success and config.get("save_on_success", True):
        name_hint = active_prompt[:20] if active_prompt else "generated_design"
        save_design(name_hint, full_design, fixed_top_tb, designs_dir, prompt=active_prompt)

if __name__ == "__main__":
    app()
