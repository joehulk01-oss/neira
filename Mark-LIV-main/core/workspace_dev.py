# workspace_dev.py
"""
workspace_dev.py — Skills workspace & developer (Blueprint Tahap 7).

Empat kemampuan dev, semuanya DIBATASI di dalam workspace Mark-LIV-main:
  analyze_repo      — peta repo: bahasa, ukuran, entry point, TODO (read-only)
  scan_logs         — baca audit/events.jsonl atau *.log → error & pola (read-only)
  run_tests         — jalankan pytest/unittest di subfolder (medium: eksekusi kode)
  backup_workspace  — arsip ZIP ke backups/ (dry-run default; tambah, TIDAK hapus)

Semua path di-resolve dan WAJIB berada di dalam workspace — path traversal
keluar workspace ditolak dengan jujur ("allowed": False + alasan).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent      # Mark-LIV-main
BACKUP_DIR = WORKSPACE / "backups"
MAX_BACKUP_BYTES = 200 * 1024 * 1024                    # 200 MB — batas aman

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist",
    "backups", ".gradle", ".idea", ".vscode", ".antigravity-ide", ".pytest_cache",
}
TEXT_SCAN_SUFFIX = {".py", ".js", ".ts", ".md", ".txt", ".yaml", ".yml"}
LOG_SUFFIX = {".jsonl", ".log", ".txt"}
ENTRY_POINTS = ["main.py", "app.py", "start.bat", "requirements.txt",
                "package.json", "pyproject.toml", "setup.py"]
LANG_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".kt": "Kotlin",
    ".java": "Java", ".c": "C", ".cpp": "C++", ".h": "C header",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".sh": "Shell", ".bat": "Batch",
    ".html": "HTML", ".css": "CSS", ".json": "JSON", ".md": "Markdown",
    ".yaml": "YAML", ".yml": "YAML", ".xml": "XML", ".sql": "SQL",
}


def _resolve_inside(target: str) -> Path | None:
    """Resolve path & pastikan DI DALAM workspace. None = tolak."""
    try:
        t = str(target or "").strip()
        p = Path(t).expanduser().resolve() if t else WORKSPACE
    except Exception:
        return None
    try:
        p.relative_to(WORKSPACE)
    except ValueError:
        return None
    return p


def _iter_files(root: Path, max_files: int = 20000):
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            yield Path(dirpath) / fn
            n += 1
            if n >= max_files:
                return


# ── 1. Analyze repo (read-only) ──────────────────────────────────────────────
def analyze_repo(target: str = "") -> dict:
    root = _resolve_inside(target)
    if root is None:
        return {"allowed": False, "reason": f"di luar workspace: {target}"}
    if not root.is_dir():
        return {"allowed": False, "reason": f"bukan folder: {root}"}

    langs: dict[str, int] = {}
    top_dirs: dict[str, int] = {}
    largest: list[tuple[int, str]] = []
    total_files = 0
    total_bytes = 0
    todos = 0
    scanned = 0

    for f in _iter_files(root):
        try:
            sz = f.stat().st_size
        except OSError:
            continue
        total_files += 1
        total_bytes += sz
        largest.append((sz, str(f)))
        rel = f.relative_to(root)
        if len(rel.parts) > 1:
            top = rel.parts[0]
            top_dirs[top] = top_dirs.get(top, 0) + 1
        ext = f.suffix.lower()
        if ext:
            langs[ext] = langs.get(ext, 0) + 1
        if ext in TEXT_SCAN_SUFFIX and sz < 200_000 and scanned < 300:
            scanned += 1
            try:
                with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        s = line.strip().upper()
                        if s.startswith("TODO") or s.startswith("FIXME"):
                            todos += 1
            except OSError:
                pass

    largest.sort(reverse=True)
    return {
        "allowed": True,
        "root": str(root),
        "total_files": total_files,
        "size_mb": round(total_bytes / 1_048_576, 2),
        "languages": langs,
        "top_dirs": top_dirs,
        "entry_points": [e for e in ENTRY_POINTS if (root / e).exists()],
        "todos": todos,
        "largest": [(round(s / 1_048_576, 2), p) for s, p in largest[:8]],
    }


# ── 2. Scan log (read-only) ──────────────────────────────────────────────────
def scan_logs(target: str = "", pattern: str = "", limit: int = 15) -> dict:
    t = str(target or "").strip()
    p = _resolve_inside(t) if t else WORKSPACE / "audit" / "events.jsonl"
    if p is None:
        return {"allowed": False, "reason": f"di luar workspace: {t}"}
    if p.is_dir():
        return {"allowed": False, "reason": f"path adalah folder: {p}"}
    if p.suffix.lower() not in LOG_SUFFIX:
        return {"allowed": False, "reason": f"ekstensi log tidak didukung: {p.suffix}"}
    if not p.exists():
        return {"allowed": True, "exists": False, "total": 0, "errors": 0,
                "recent": [], "note": f"{p.name} belum ada — belum ada jejak"}

    total = 0
    errors = 0
    recent: list[str] = []
    pat = (pattern or "").lower()
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                if pat and pat not in line.lower():
                    continue
                total += 1
                ev = {}
                try:
                    import json
                    ev = json.loads(line)
                except Exception:
                    ev = {}
                if ev.get("result") in ("failed", "denied", "error"):
                    errors += 1
                if len(recent) < limit or errors and ev.get("result") in ("failed", "denied"):
                    ts = ev.get("ts") or ev.get("timestamp") or "?"
                    recent.append(f"{ts} | {ev.get('skill', '?')}."
                                  f"{ev.get('action', '?')} | {ev.get('result', '?')}")
    except OSError as e:
        return {"allowed": True, "exists": True, "total": 0, "errors": 0,
                "recent": [], "note": f"gagal baca: {e}"}

    return {"allowed": True, "exists": True, "path": str(p), "total": total,
            "errors": errors, "recent": recent[-limit:],
            "pattern": pat or "(semua)"}


# ── 3. Run tests (medium: eksekusi kode workspace sendiri) ───────────────────
def run_tests(target: str = "", timeout: int = 180) -> dict:
    root = _resolve_inside(target)
    if root is None:
        return {"allowed": False, "reason": f"di luar workspace: {target}"}
    if not root.is_dir():
        return {"allowed": False, "reason": f"bukan folder: {root}"}

    has_pytest = importlib.util.find_spec("pytest") is not None
    if has_pytest:
        cmd = [sys.executable, "-m", "pytest", "-q", str(root)]
        runner = "pytest"
    else:
        cmd = [sys.executable, "-m", "unittest", "discover",
               "-s", str(root), "-t", str(root), "-p", "test_*.py", "-v"]
        runner = "unittest"

    t0 = time.time()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, env=env)
        rc = proc.returncode
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return {"allowed": True, "ok": False, "runner": runner,
                "duration": float(timeout), "output": f"⏱️ timeout > {timeout}s"}
    tail = "\n".join(out.strip().splitlines()[-40:])
    return {"allowed": True, "ok": rc == 0, "returncode": rc, "runner": runner,
            "duration": round(time.time() - t0, 1), "output": tail}


# ── 4. Backup workspace (dry-run default; tambah, TIDAK hapus) ───────────────
def backup_workspace(target: str = "", dry_run: bool = True) -> dict:
    root = _resolve_inside(target)
    if root is None:
        return {"allowed": False, "reason": f"di luar workspace: {target}"}

    files: list[tuple[Path, int]] = []
    for f in _iter_files(root):
        if BACKUP_DIR in f.parents:
            continue                              # jangan backup backup
        try:
            files.append((f, f.stat().st_size))
        except OSError:
            pass
    total = sum(s for _, s in files)
    if total > MAX_BACKUP_BYTES and not dry_run:
        # Dry-run TIDAK pernah menolak (tidak menulis apa pun) —
        # penolakan batas hanya untuk penulisan sungguhan.
        return {"allowed": True, "ok": False,
                "refused": f"ukuran {round(total / 1_048_576, 1)} MB > "
                           f"batas {MAX_BACKUP_BYTES // 1_048_576} MB",
                "files": len(files), "bytes": total}

    stamp = time.strftime("%Y%m%d-%H%M%S")
    label = root.name if root != WORKSPACE else "workspace"
    dest = BACKUP_DIR / f"{label}-backup-{stamp}.zip"

    if dry_run:
        return {"allowed": True, "ok": True, "dry_run": True,
                "files": len(files), "bytes": total, "dest": str(dest),
                "note": "dry-run — tidak ada file ditulis"}

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for f, _ in files:
            zf.write(f, f.relative_to(root))
    return {"allowed": True, "ok": True, "dry_run": False, "files": len(files),
            "bytes": total, "dest": str(dest),
            "size_mb": round(dest.stat().st_size / 1_048_576, 2)}


def list_backups() -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    rows = []
    for f in BACKUP_DIR.glob("*.zip"):
        try:
            st = f.stat()
            rows.append({"name": f.name,
                         "size_mb": round(st.st_size / 1_048_576, 2),
                         "modified": time.strftime(
                             "%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
        except OSError:
            continue
    rows.sort(key=lambda r: r["modified"], reverse=True)
    return rows
