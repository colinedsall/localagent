import ollama
import re
from typing import Optional, Dict

class VerilogAgent:
    def __init__(self, model_name: str = "qwen2.5-coder:14b", extra_instructions: str = ""):
        self.model_name = model_name
        self.system_prompt = (
            "You are acting as an expert Computer Hardware Engineer specializing in Verilog (hardware description language)."
            "Your goal is to write Synthesizable Verilog 2001 code. "
            "Follow these explicit rules:\n"
            "1. Use `module` and `endmodule` explicitly.\n"
            "2. Use `parameter` for configurable widths.\n"
            "3. Use synchronous active-high reset unless specified otherwise.\n"
            "4. Always use non-blocking assignments (`<=`) in sequential logic and blocking (`=`) in combinational logic.\n"
            "5. Do NOT output markdown backticks (```verilog) if possible, or ensure they are easily parseable.\n"
            "6. Output ONLY the code when requested. All code must be contained within a single code block, not multiple code blocks or files.\n"
            "7. You are to avoid using System Verilog at all times, including making common mistakes such as declaring variables in initial blocks."
        )
        if extra_instructions:
            self.system_prompt += f"\n\nADDITIONAL INSTRUCTIONS:\n{extra_instructions}"

    def _clean_response(self, text: str) -> str:
        """Extracts code from markdown blocks if present."""
        match = re.search(r"```verilog\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        match = re.search(r"```\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
            
        return text.strip()

    def generate_design(self, user_prompt: str) -> str:
        """Generates the Verilog module based on user requirements."""
        full_prompt = (
            f"Write a Verilog module for the following requirement: {user_prompt}.\n"
            "Ensure the interface signals are clearly defined."
        )
        
        response = ollama.chat(model=self.model_name, messages=[
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': full_prompt},
        ])
        
        return self._clean_response(response['message']['content'])

    def generate_testbench(self, original_verilog: str) -> str:
        """Generates a self-checking testbench for the given design."""
        tb_prompt = (
            "Write a self-checking Verilog testbench for the following module.\n"
            "1. Instantiate the Unit Under Test (UUT).\n"
            "2. Generate a clock (if sequential).\n"
            "3. Apply test vectors covering corner cases.\n"
            "4. Use `$display` and `$error` to report pass/fail.\n"
            "5. End simulation with `$finish`.\n"
            "6. DO NOT include the design module code in your response. Only the testbench.\n"
            "7. The testbench module name must be `tb_<module_name>` or similar.\n\n"
            f"--- Design Under Test ---\n{original_verilog}"
        )

        response = ollama.chat(model=self.model_name, messages=[
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': tb_prompt},
        ])
        
        return self._clean_response(response['message']['content'])

    def fix_design(self, original_code: str, error_log: str, is_testbench: bool = False) -> str:
        """Iteratively fixes code based on compiler error logs."""
        file_type = "testbench" if is_testbench else "module"
        fix_prompt = (
            f"The following Verilog {file_type} produced compilation errors.\n"
            "Please fix the code. Return ONLY the full corrected code.\n"
        )
        
        if is_testbench:
            fix_prompt += "DO NOT include the design module code. Output ONLY the testbench module.\n"

        fix_prompt += (
            f"--- Error Log ---\n{error_log}\n\n"
            f"--- Original Code ---\n{original_code}"
        )
        
        response = ollama.chat(model=self.model_name, messages=[
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': fix_prompt},
        ])
        
        return self._clean_response(response['message']['content'])
