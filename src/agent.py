import ollama
import re
import requests
import abc
from typing import Optional, Dict, List

# --- Backends ---

class LLMBackend(abc.ABC):
    @abc.abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generates a response from the LLM."""
        pass

class OllamaBackend(LLMBackend):
    def __init__(self, model_name: str):
        self.model_name = model_name

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = ollama.chat(model=self.model_name, messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ])
            return response['message']['content']
        except Exception as e:
            return f"OLLAMA ERROR: {str(e)}"

class HuggingFaceBackend(LLMBackend):
    def __init__(self, model_name: str, api_key: str, api_url: Optional[str] = None):
        self.model_name = model_name
        self.api_key = api_key
        # Default to the new Router URL
        if not api_url:
            self.api_url = "https://router.huggingface.co/v1/chat/completions"
        else:
            self.api_url = api_url

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # OpenAI-compatible payload
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 4096,
            "temperature": 0.5,
            "stream": False
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            result = response.json()
            
            # Parse OpenAI-style response
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content']
            elif 'error' in result:
                 return f"HF API ERROR: {result['error']}"
            else:
                 return f"HF UNEXPECTED RESPONSE: {str(result)}"
            
        except requests.exceptions.HTTPError as e:
            return f"HF API HTTP ERROR: {e}\nResponse: {response.text}"
        except Exception as e:
            return f"HF API ERROR: {str(e)}"

# --- Agent ---

class VerilogAgent:
    def __init__(self, model_name: str = "qwen2.5-coder:14b", extra_instructions: str = "", config: Optional[Dict] = None):
        self.model_name = model_name
        
        # Initialize Backend based on config
        self.backend = self._init_backend(model_name, config)

        self.system_prompt = (
            "You are acting as an expert Computer Hardware Engineer specializing in Verilog (hardware description language)."
            "Your goal is to write Synthesizable Verilog 2001 code. "
            "Follow these explicit rules:\n"
            "1. Use `module` and `endmodule` explicitly.\n"
            "2. Use `parameter` for configurable widths.\n"
            "3. Use synchronous active-high reset unless specified otherwise.\n"
            "4. Always use non-blocking assignments (`<=`) in sequential logic and blocking (`=`) in combinational logic.\n"
            "5. Do NOT output markdown backticks (```verilog) if possible. Just output the raw code. However, you MUST preserve the backtick character (`) for Verilog compiler directives like `timescale` and `define`.\n"
            "6. Output ONLY the code when requested. All code must be contained within a single code block, not multiple code blocks or files.\n"
            "7. You are to avoid using System Verilog at all times.\n"
            "8. You are to avoid making common mistakes such as declaring variables in initial or always blocks, especially in generated sequential logic.\n"
            "9. STRUCTURAL OUTPUT RULE: All module outputs MUST be of type `wire`. Do NOT use `output reg`. Instead, declare an internal `reg`, assign to it in your logic, and drive the output `wire` with an `assign` statement (e.g., `output out; reg out_reg; assign out = out_reg;`).\n"
            "10. MODULARITY RULE: For complex designs, break functionality into smaller submodules (e.g., ALU, Control Unit, Datapath) and instantiate them in the top-level module."
        )
        if extra_instructions:
            self.system_prompt += f"\n\nADDITIONAL INSTRUCTIONS:\n{extra_instructions}"

    def _init_backend(self, cli_model: str, config: Optional[Dict]) -> LLMBackend:
        """Selects and initializes the appropriate LLM backend."""
        # Defaults
        provider = "ollama"
        model = cli_model  # CLI overrides everything if present
        api_key = ""
        api_url = ""

        if config and "llm" in config:
            llm_cfg = config["llm"]
            provider = llm_cfg.get("provider", "ollama").lower()
            
            # If sub-dict exists for the provider, grab settings from there
            if provider in llm_cfg and isinstance(llm_cfg[provider], dict):
                p_cfg = llm_cfg[provider]
                # Use CLI model if given, else config model, else default
                if not model:
                     base_model = p_cfg.get("model", "qwen2.5-coder:14b")
                     variant = p_cfg.get("variant", "")
                     if variant:
                         model = f"{base_model}-{variant}"
                     else:
                         model = base_model
                api_key = p_cfg.get("api_key", "")
                api_url = p_cfg.get("api_url", "")
            else:
                # Fallback to flat structure (backward compatibility)
                if not model:
                    model = llm_cfg.get("model", "qwen2.5-coder:14b")
                api_key = llm_cfg.get("api_key", "")
                api_url = llm_cfg.get("api_url", "")

        if provider == "huggingface":
            if not api_key:
                print("WARNING: Hugging Face provider selected but no `api_key` found in config.yaml.")
            return HuggingFaceBackend(model_name=model, api_key=api_key, api_url=api_url)
        else:
            return OllamaBackend(model_name=model)

    def _clean_response(self, text: str) -> str:
        """Extracts code from markdown blocks if present."""
        match = re.search(r"```verilog\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        match = re.search(r"```\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
            
        return text.strip()

    def generate_plan(self, user_prompt: str) -> list[dict]:
        """
        Decomposes a complex design request into a structured implementation plan.
        Returns a list of dicts: [{'name': 'alu', 'description': '...', 'type': 'submodule'}, ...]
        """
        plan_prompt = (
            f"Analyze the following Verilog design requirement: '{user_prompt}'.\n"
            "Break this down into a modular implementation plan.\n"
            "Identify the necessary submodules (e.g., ALU, Counters, FSMs) and the top-level module.\n"
            "Return a strictly formatted line-by-line list.\n"
            "Format:\n"
            "MODULE: <module_name> | TYPE: <submodule/top> | DESC: <brief description of functionality>\n\n"
            "Example:\n"
            "MODULE: alu | TYPE: submodule | DESC: 16-bit ALU with add/sub/logic ops\n"
            "MODULE: cpu_top | TYPE: top | DESC: Top level connecting ALU and Controller\n"
            "Order the modules by dependency (independent submodules first, top module last)."
        )

        raw_plan = self.backend.generate(self.system_prompt, plan_prompt)
        
        plan = []
        for line in raw_plan.split('\n'):
            if "MODULE:" in line:
                try:
                    parts = line.split('|')
                    name = parts[0].split(':')[1].strip()
                    m_type = parts[1].split(':')[1].strip().lower()
                    desc = parts[2].split(':')[1].strip()
                    plan.append({'name': name, 'type': m_type, 'description': desc})
                except Exception:
                    continue
        
        if not plan:
            # Fallback for simple designs or failed parsing
            # If backend returned an error string, this might fail weirdly, but that's handled in loop
            return [{'name': 'design', 'type': 'top', 'description': user_prompt}]
            
        return plan

    def generate_design(self, user_prompt: str, context: str = "") -> str:
        """Generates the Verilog module based on user requirements and optional context."""
        full_prompt = (
            f"Write a Verilog module for the following requirement: {user_prompt}.\n"
            "Ensure the interface signals are clearly defined.\n"
        )
        if context:
            full_prompt += f"\n\nCONTEXT (Related Modules):\n{context}\n\nUse the above modules if relevant."
        
        response = self.backend.generate(self.system_prompt, full_prompt)
        return self._clean_response(response)

    def _extract_module_name(self, verilog_code: str) -> str:
        """Extracts the module name from Verilog code."""
        match = re.search(r"^\s*module\s+(\w+)", verilog_code, re.MULTILINE)
        if match:
            return match.group(1)
        return "generated_module" # Fallback

    def generate_testbench(self, original_verilog: str) -> str:
        """Generates a self-checking testbench for the given design."""
        module_name = self._extract_module_name(original_verilog)
        tb_prompt = (
            "Write a robust, self-checking Verilog testbench for the following module.\n"
            f"1. Instantiate the Unit Under Test (UUT) named `{module_name}`.\n"
            "2. Generate a clock (if sequential) with a ~10ns period.\n"
            "3. Proper Reset: Hold reset active for at least 20ns (2 cycles) at the start.\n"
            "4. TIMING IS CRITICAL: When checking sequential outputs, ALWAYS wait for a short delay (e.g., `#1` or `@(negedge clk)`) after the active clock edge to avoid race conditions. NEVER check immediately at the same edge active edge.\n"
            "5. Apply diverse test vectors covering corner cases.\n"
            "6. Use `$display` and `$error` to report pass/fail status explicitly for each test case.\n"
            "7. End simulation with `$finish` after all tests.\n"
            "   - VERIFICATION STRATEGY: \n"
            "     * For COMPLEX logic (ALUs, Multipliers, FSMs): Do NOT hardcode expected results. Write a `task` or `function` (Behavioral Golden Model) to calculate expected output.\n"
            "     * For SIMPLE modules (Flip-Flops, Registers, Basic Gates, Muxes): Simple direct assertions or hardcoded checks are acceptable. Do NOT over-engineer the testbench.\n"
            "8. DO NOT include the design module code in your response. Only the testbench.\n"
            "9. You MUST preserve the backtick character (`) for Verilog compiler directives like `timescale` and `define`.\n"
            "10. The testbench module name must be `tb_<module_name>` or similar.\n\n"
            f"--- Design Under Test ---\n{original_verilog}"
        )

        response = self.backend.generate(self.system_prompt, tb_prompt)
        return self._clean_response(response)

    def fix_design(self, original_code: str, error_log: str, is_testbench: bool = False) -> str:
        """Iteratively fixes code based on compiler error logs."""
        file_type = "testbench" if is_testbench else "module"
        fix_prompt = (
            f"The following Verilog {file_type} produced compilation errors.\n"
            "Please fix the code. Return ONLY the full corrected code.\n"
            "If the error is due to a missing timescale directive, use 1ns/1ps.\n"
            "If the error is due to a logic problem, identify the logic error and fix it.\n"
            "If the error is due to a static variable initialization or variable declaration, ensure that they are declared outside of any blocks, such as in the top of the module.\n"
            "If the output log cites requiring SystemVerilog, ensure that both variable declarations and logic are compatible with Verilog 2001, especially variable declarations NOT in blocks.\n"
            "CRITICAL: You MUST modify the code to fix the error. Do NOT return the same code.\n"
        )
        
        if is_testbench:
            fix_prompt += "DO NOT include the design module code. Output ONLY the testbench module.\n"
            fix_prompt += "If the error output shows consistent incorrect logic due to timing or expected outputs, implement changes to the testbench to allow for more lenient timing constraints.\n"  

        # --- Context Extractor ---
        # Look for "filename.v:123:" patterns in the error log
        code_lines = original_code.split('\n')
        error_lines = set()
        for match in re.finditer(r":(\d+):", error_log):
            try:
                line_idx = int(match.group(1)) - 1
                if 0 <= line_idx < len(code_lines):
                    error_lines.add(line_idx)
            except ValueError:
                continue

        if error_lines:
            fix_prompt += "\n--- FOCUS ON THESE LINES (Suspected Syntax/Compilation Errors) ---\n"
            for idx in sorted(list(error_lines)):
                # Provide 1 line of context before/after if possible
                start_ctx = max(0, idx - 1)
                end_ctx = min(len(code_lines), idx + 2)
                for i in range(start_ctx, end_ctx):
                    marker = ">> " if i == idx else "   "
                    fix_prompt += f"{marker}{i+1}: {code_lines[i]}\n"
            fix_prompt += "------------------------------------------------------------\n\n"
        # -------------------------

        fix_prompt += (
            f"--- Error Log ---\n{error_log}\n\n"
            f"--- Original Code ---\n{original_code}"
        )
        
        response = self.backend.generate(self.system_prompt, fix_prompt)
        return self._clean_response(response)

    def fix_testbench_logic(self, testbench_code: str, design_code: str, error_log: str) -> str:
        """Specialized fixer for Testbench logic errors using a Verification Expert persona."""
        module_name = self._extract_module_name(design_code)

        verification_system_prompt = (
            "You are an expert Verification Engineer. Your goal is to debug and fix a Verilog Testbench.\n"
            "You are given:\n"
            "1. The Design Under Test (DUT) code (assume this is likely correct logic-wise).\n"
            "2. The Testbench code (which is failing).\n"
            "3. The Simulation Output/Error Log.\n"
            "Your task is to analyze the failure and FIX the testbench to correctly verify the design.\n"
            f"CRITICAL: Ensure that the testbench instantiates the module named `{module_name}` correctly.\n"
            "Common Testbench Issues to look for:\n"
            "- Timing Mismatches: Checking outputs too early (race conditions). Use `#1` delay or check on `negedge clk`.\n"
            "- Reset Issues: Not holding reset long enough or checking values during reset.\n"
            "- Latency: The design may be pipelined (taking N cycles), but the testbench expects 0-cycle response.\n"
            "- Protocol: Misunderstanding valid/ready signals.\n"
            "- Golden Model Mismatch: Avoid hardcoding expected values. Instead, implement a behavioral model (Golden Model) in the testbench to CALCULATE the expected output on the fly based on inputs.\n"
            "Output ONLY the fixed Testbench code.\n"
            "CRITICAL: You MUST modify the code to fix the verification failure. Do NOT return the same code."
        )

        user_prompt = (
            "The testbench simulation failed. Fix the testbench logic to match the DUT behavior.\n\n"
            f"--- Simulation Output/Error Log ---\n{error_log}\n\n"
            f"--- Design Under Test (DUT) ---\n{design_code}\n\n"
            f"--- Current Testbench ---\n{testbench_code}"
        )

        response = self.backend.generate(verification_system_prompt, user_prompt)
        return self._clean_response(response)
