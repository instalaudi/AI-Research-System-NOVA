import subprocess
import tempfile
import os
import sys
import time
from typing import Dict, Any

import ast

class CodeSandbox:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        # FIX-C1: Massively expanded blocklist to prevent trivial sandbox escapes
        self.blocked_keywords = [
            'os.', 'subprocess', 'shutil', 'pickle', 'marshal', 'shelve',
            'rmdir', 'unlink', 'remove', 'system(', 'popen', 'exec(', 'eval(',
            '__import__', 'getattr', 'setattr', 'globals(', 'locals(', 'builtins',
            'importlib', 'open(', 'socket', 'ctypes', 'compile(', 'breakpoint',
            'webbrowser', 'urllib', 'requests', 'http.client', 'ftplib',
            'telnetlib', 'smtplib', 'tempfile', 'pathlib', 'io.open',
            'codecs.open', 'signal', 'multiprocessing', 'threading',
            '__dict__', '__class__', '__base__', '__subclasses__', 'type('
        ]
        # Modules that are never safe to import
        self._blocked_modules = {
            'os', 'subprocess', 'shutil', 'socket', 'ctypes', 'importlib',
            'sys', 'signal', 'multiprocessing', 'threading', 'webbrowser',
            'urllib', 'http', 'ftplib', 'telnetlib', 'smtplib', 'pickle',
            'marshal', 'shelve', 'tempfile', 'pathlib', 'io', 'codecs',
            'core.database', 'core.auth', 'core.dependencies', 'core.context_manager',
            'database', 'auth', 'core.orchestrator', 'core.config'
        }
        # Attributes that are never safe to access
        self._blocked_attrs = {
            '__builtins__', '__dict__', '__class__', '__base__', '__subclasses__',
            '__mro__', '__subclasscheck__', '__init__', '__new__', '__globals__',
            '__code__', 'func_globals', 'func_code', '__module__', '__defaults__',
            '__kwdefaults__', '__closure__', '__annotations__', '__name__', '__getattribute__'
        }
        self._blocked_js_ts_keywords = {
            'require(', 'import ', 'process.', 'child_process', 'eval(', 'Function(',
            'setTimeout(', 'setInterval(', 'fetch(', 'XMLHttpRequest', 'WebSocket',
            'window.', 'globalThis', 'Deno', 'fs.', 'net.', 'http.', 'https.',
            'os.', 'spawn(', 'exec(', 'execSync', 'fork(', 'worker_threads', 'process.env'
        }

    def _is_module_blocked(self, module_name: str) -> bool:
        """Indicates if a module or any of its parents are in the blocklist."""
        if not module_name: return False
        parts = module_name.split('.')
        current = ""
        for part in parts:
            current = f"{current}.{part}" if current else part
            if current in self._blocked_modules:
                return True
        return False

    def _is_safe_code(self, code: str, language: str) -> bool:
        """
        Scans code for dangerous patterns. 
        For Python, it also uses AST to ensure no forbidden primitives are used.
        """
        # Basic keyword block
        code_lower = code.lower()
        for kw in self.blocked_keywords:
            if kw in code_lower:
                return False
        
        if language == "python":
            try:
                # AST check for forbidden calls and imports
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    # Block dangerous function calls
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Attribute):
                            if isinstance(node.func.value, ast.Name) and node.func.value.id in ['os', 'subprocess', 'shutil']:
                                return False
                        elif isinstance(node.func, ast.Name):
                            if node.func.id in ['eval', 'exec', '__import__', 'open', 'compile', 'breakpoint', 'getattr', 'setattr', 'hasattr', 'delattr']:
                                return False
                    # Block dangerous attribute access (e.g. obj.__dict__)
                    elif isinstance(node, ast.Attribute):
                        if node.attr in self._blocked_attrs or (node.attr.startswith('__') and node.attr.endswith('__')):
                            return False
                    # Block lambda expressions to prevent anonymous function escapes
                    elif isinstance(node, ast.Lambda):
                        return False
                    # Block dangerous strings that look like obfuscated function names
                    elif isinstance(node, (ast.Constant, ast.Str)):
                        val = node.value if isinstance(node, ast.Constant) else node.s
                        if isinstance(val, str):
                            # Very basic check for obfuscated builtins
                            if any(b in val for b in ['eval', 'exec', '__import__', 'os.system', 'subprocess', 'open', 'importlib']):
                                return False
                    # FIX-C1: Block dangerous imports via AST
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if self._is_module_blocked(alias.name):
                                return False
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and self._is_module_blocked(node.module):
                            return False
            except Exception:
                return False # If code doesn't parse, don't run it
        elif language in ["javascript", "typescript"]:
            # Additional guarding for JS/TS, since we don't have an AST parser here.
            for kw in self._blocked_js_ts_keywords:
                if kw in code_lower:
                    return False
            # Block import/require statements and any attempt to reach process or file APIs.
            if any(x in code_lower for x in ['require(', 'import ', 'process.', 'child_process', 'fs.', 'fetch(', 'globalthis', 'window.', 'document', 'new function', 'eval(']):
                return False

        return True

    def _get_clean_env(self) -> Dict[str, str]:
        """Provides a minimal environment, scrubbing sensitive API keys."""
        # Only keep basic path and standard vars
        safe_keys = ['PATH', 'SYSTEMROOT', 'TEMP', 'TMP', 'USERPROFILE']
        env = {k: os.environ[k] for k in safe_keys if k in os.environ}
        env['PYTHONIOENCODING'] = 'utf-8'
        return env

    async def execute_python(self, code: str) -> Dict[str, Any]:
        """Executes python code and returns stdout/stderr/exit_code."""
        # GUARD-01: Pre-execution scan
        if not self._is_safe_code(code, "python"):
            return {"stdout": "", "stderr": "Security Error: Dangerous code pattern detected.", "exit_code": -1, "success": False}

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode='w', encoding='utf-8') as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            start_time = time.time()
            # We run it as a separate process with a scrubbed environment
            import asyncio
            process = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.timeout,
                env=self._get_clean_env()
            )
            runtime = time.time() - start_time
            
            return {
                "stdout": process.stdout,
                "stderr": process.stderr,
                "exit_code": process.returncode,
                "runtime": round(runtime, 3),
                "success": process.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Error: Execution timed out after {self.timeout}s",
                "exit_code": -1,
                "success": False
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Unexpected error: {str(e)}",
                "exit_code": -1,
                "success": False
            }
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass

    async def execute_js(self, code: str) -> Dict[str, Any]:
        """Executes JavaScript code using Node.js."""
        # GUARD-01: Pre-execution scan
        if not self._is_safe_code(code, "javascript"):
            return {"stdout": "", "stderr": "Security Error: Dangerous code pattern detected.", "success": False}

        with tempfile.NamedTemporaryFile(suffix=".js", delete=False, mode='w', encoding='utf-8') as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            start_time = time.time()
            import asyncio
            process = await asyncio.to_thread(
                subprocess.run,
                ["node", tmp_path],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.timeout,
                env=self._get_clean_env()
            )
            runtime = time.time() - start_time
            
            return {
                "stdout": process.stdout,
                "stderr": process.stderr,
                "exit_code": process.returncode,
                "runtime": round(runtime, 3),
                "success": process.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"Error: JS execution timed out after {self.timeout}s", "success": False}
        except Exception as e:
            return {"stdout": "", "stderr": f"JS Error: {str(e)}", "success": False}
        finally:
            if os.path.exists(tmp_path): os.unlink(tmp_path)

    async def execute_ts(self, code: str) -> Dict[str, Any]:
        """
        Executes TypeScript code. 
        """
        # GUARD-01: Pre-execution scan
        if not self._is_safe_code(code, "typescript"):
            return {"stdout": "", "stderr": "Security Error: Dangerous code pattern detected.", "success": False}

        # For simplicity and speed, we'll use ts-node if installed, or treat as JS (many TS snippets are valid JS)
        with tempfile.NamedTemporaryFile(suffix=".ts", delete=False, mode='w', encoding='utf-8') as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            start_time = time.time()
            # Attempt with npx ts-node for zero-config execution if node is present
            import asyncio
            process = await asyncio.to_thread(
                subprocess.run,
                ["npx", "ts-node", "--skip-project", tmp_path],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.timeout + 10, # TS takes longer to compile
                env=self._get_clean_env()
            )
            runtime = time.time() - start_time
            
            return {
                "stdout": process.stdout,
                "stderr": process.stderr,
                "exit_code": process.returncode,
                "runtime": round(runtime, 3),
                "success": process.returncode == 0
            }
        except Exception as e:
            # Fallback: maybe it's just JS?
            return await self.execute_js(code)
        finally:
            if os.path.exists(tmp_path): os.unlink(tmp_path)

sandbox = CodeSandbox()
