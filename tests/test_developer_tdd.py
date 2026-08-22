"""
Pruebas Unitarias Automatizadas para Code Sandbox & Ciclo TDD de DeveloperAgent (Fase 2)
"""

import pytest
from core.code_sandbox import CodeSandbox
from agents.developer_agent import DeveloperAgent


def test_sandbox_validate_syntax_valid():
    """Valida que código Python y JSON correcto sea aprobado sintácticamente."""
    sandbox = CodeSandbox()
    files = {
        "main.py": "def add(a: int, b: int) -> int:\n    return a + b\n\nprint(add(2, 3))\n",
        "config.json": '{"app": "nova", "version": 14.0, "active": true}'
    }
    res = sandbox.validate_syntax(files)
    assert res["valid"] is True
    assert res["error_count"] == 0


def test_sandbox_validate_syntax_invalid():
    """Valida la detección de SyntaxError y JSONDecodeError con metadatos de línea."""
    sandbox = CodeSandbox()
    files = {
        "broken.py": "def invalid_syntax(:\n    pass",
        "broken.json": '{"unclosed_string": "value'
    }
    res = sandbox.validate_syntax(files)
    assert res["valid"] is False
    assert res["error_count"] == 2
    
    error_files = [e["file"] for e in res["errors"]]
    assert "broken.py" in error_files
    assert "broken.json" in error_files


def test_sandbox_run_passing_tests():
    """Valida la ejecución exitosa de pruebas unitarias en el sandbox aislado."""
    sandbox = CodeSandbox()
    files = {
        "calculator.py": "def multiply(x, y):\n    return x * y\n",
        "test_calculator.py": """
import unittest
from calculator import multiply

class TestCalc(unittest.TestCase):
    def test_multiply(self):
        self.assertEqual(multiply(3, 4), 12)

if __name__ == '__main__':
    unittest.main()
"""
    }
    res = sandbox.run_tests_in_sandbox(files)
    assert res["success"] is True
    assert res.get("error_trace") is None


def test_sandbox_run_failing_tests():
    """Valida que una aserción fallida sea capturada y devuelva el traceback exacto."""
    sandbox = CodeSandbox()
    files = {
        "calculator.py": "def multiply(x, y):\n    return x + y  # Bug intencional\n",
        "test_calculator.py": """
import unittest
from calculator import multiply

class TestCalc(unittest.TestCase):
    def test_multiply(self):
        self.assertEqual(multiply(3, 4), 12)

if __name__ == '__main__':
    unittest.main()
"""
    }
    res = sandbox.run_tests_in_sandbox(files)
    assert res["success"] is False
    assert res.get("error_trace") is not None
    assert "AssertionError" in str(res.get("error_trace"))


def test_ensure_standard_artifacts():
    """Valida la inclusión automática de Dockerfile y README.md."""
    initial_files = {
        "main.py": "print('Hello NOVA')\n",
        "requirements.txt": "fastapi>=0.100.0\n"
    }
    enhanced = DeveloperAgent._ensure_standard_artifacts(initial_files, "Crear una API REST")
    
    assert "README.md" in enhanced
    assert "Dockerfile" in enhanced
    assert "Crear una API REST" in enhanced["README.md"]
    assert "FROM python:3.12-slim" in enhanced["Dockerfile"]
