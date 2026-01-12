import subprocess
import os
from pathlib import Path
from typing import Tuple, Optional

class VerilogSimulator:
    def __init__(self, work_dir: str = "workspace"):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(exist_ok=True)

    def run_simulation(self, design_code: str, tb_code: str, module_name: str) -> Tuple[bool, str]:
        """
        Compiles and runs the simulation.
        Returns: (success: bool, output: str)
        """
        design_file = self.work_dir / f"{module_name}.v"
        tb_file = self.work_dir / f"{module_name}_tb.v"
        sim_out = self.work_dir / f"{module_name}.out"

        # Write files
        with open(design_file, "w") as f:
            f.write(design_code)
        with open(tb_file, "w") as f:
            f.write(tb_code)

        # 1. Compile with iverilog
        compile_cmd = ["iverilog", "-o", str(sim_out), str(design_file), str(tb_file)]
        result = subprocess.run(compile_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return False, f"COMPILATION ERROR:\n{result.stderr}"

        # 2. Run simulation with vvp
        sim_cmd = ["vvp", str(sim_out)]
        try:
            sim_result = subprocess.run(sim_cmd, capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            return False, "TIMEOUT ERROR: Simulation exceeded 10 seconds. Likely infinite loop (missing $finish) or clock logic error."

        if sim_result.returncode != 0:
            return False, f"RUNTIME ERROR:\n{sim_result.stderr}\nSTDOUT:\n{sim_result.stdout}"
        
        # Check for error keywords in stdout (basic self-checking support)
        if "ERROR" in sim_result.stdout or "FAIL" in sim_result.stdout:
             return False, f"TESTBENCH FAILURE:\n{sim_result.stdout}"

        return True, f"SIMULATION SUCCESS:\n{sim_result.stdout}"
