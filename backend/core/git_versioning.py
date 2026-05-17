"""
Versionado Git automático y seguro para entorno local single-user.
Realiza commits solo de rutas explícitas para evitar incluir cambios no relacionados.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from core.logging_config import get_logger

logger = get_logger("core.git_versioning")


class GitVersioning:
    def __init__(self, start_path: Optional[str] = None):
        self.start_path = Path(start_path or ".").resolve()
        self.repo_root = self._detect_repo_root()

    def _detect_repo_root(self) -> Optional[Path]:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(self.start_path),
                capture_output=True,
                text=True,
                errors="replace",
                check=True
            )
            return Path(result.stdout.strip()).resolve()
        except Exception:
            return None

    def is_available(self) -> bool:
        return self.repo_root is not None

    def auto_commit_paths(self, paths: List[str], message: str) -> Dict[str, str]:
        """
        Crea commit local con rutas específicas. No usa add -A.
        """
        if not self.repo_root:
            return {"status": "skipped", "reason": "not_a_git_repo"}

        valid_paths: List[str] = []
        for raw_path in paths:
            abs_path = Path(raw_path).resolve()
            if not abs_path.exists():
                continue
            try:
                rel = abs_path.relative_to(self.repo_root)
                valid_paths.append(str(rel).replace("\\", "/"))
            except Exception:
                continue

        if not valid_paths:
            return {"status": "skipped", "reason": "no_valid_paths"}

        try:
            subprocess.run(
                ["git", "add", "--"] + valid_paths,
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True,
                errors="replace"
            )

            staged_check = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                errors="replace"
            )
            if staged_check.returncode == 0:
                return {"status": "skipped", "reason": "no_staged_changes"}

            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True,
                errors="replace"
            )
            logger.info(f"Auto-commit creado: {message}")
            return {"status": "committed", "message": message}
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            logger.warning(f"No se pudo crear auto-commit: {stderr}")
            return {"status": "error", "reason": stderr or "git_failed"}
        except Exception as e:
            logger.warning(f"Fallo inesperado en auto-commit: {e}")
            return {"status": "error", "reason": str(e)}

    def get_history(self, limit: int = 20, path_filter: Optional[str] = None) -> Dict[str, object]:
        if not self.repo_root:
            return {"status": "error", "message": "not_a_git_repo", "commits": []}
        try:
            cmd = ["git", "log", f"-{max(1, min(limit, 200))}", "--pretty=format:%H|%s|%ai|%an"]
            if path_filter:
                cmd.extend(["--", path_filter])
            result = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                errors="replace",
                check=False
            )
            if result.returncode != 0:
                return {"status": "error", "message": (result.stderr or "git_log_failed").strip(), "commits": []}
            commits = []
            for line in (result.stdout or "").splitlines():
                parts = line.split("|", 3)
                if len(parts) != 4:
                    continue
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "date": parts[2],
                    "author": parts[3]
                })
            return {"status": "success", "count": len(commits), "commits": commits}
        except Exception as e:
            return {"status": "error", "message": str(e), "commits": []}

    def get_diff(self, commit_hash: str) -> Dict[str, object]:
        if not self.repo_root:
            return {"status": "error", "message": "not_a_git_repo", "diff": ""}
        if not commit_hash or len(commit_hash) < 6:
            return {"status": "error", "message": "invalid_commit_hash", "diff": ""}
        try:
            result = subprocess.run(
                ["git", "show", "--stat", "--patch", "--no-color", commit_hash],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                errors="replace",
                check=False
            )
            if result.returncode != 0:
                return {"status": "error", "message": (result.stderr or "git_show_failed").strip(), "diff": ""}
            return {"status": "success", "hash": commit_hash, "diff": result.stdout}
        except Exception as e:
            return {"status": "error", "message": str(e), "diff": ""}


git_versioning = GitVersioning()
