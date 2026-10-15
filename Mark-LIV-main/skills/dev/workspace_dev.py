# workspace_dev.py (skill wrapper) — Blueprint Tahap 7
"""
Pintu skill untuk core/workspace_dev — dengan 3 gerbang wajib:
emergency stop → policy gate (workspace.* / logs.* / devtools.*) → audit.

Pemakaian dari Hermes/model:
    {"action": "workspace_dev", "cmd": "analyze"}
    {"action": "workspace_dev", "cmd": "analyze", "target": "core"}
    {"action": "workspace_dev", "cmd": "logs", "pattern": "deny"}
    {"action": "workspace_dev", "cmd": "tests", "target": "scratch/tmp_t7"}
    {"action": "workspace_dev", "cmd": "backup"}                     # dry-run
    {"action": "workspace_dev", "cmd": "backup", "confirm": true}    # tulis zip
    {"action": "workspace_dev", "cmd": "backups"}                    # daftar
"""
from __future__ import annotations

try:
    from core import workspace_dev as _wd
except Exception:
    _wd = None
try:
    from core.policy_engine import decide as _decide
except Exception:
    _decide = None
try:
    from core.audit_logger import log_event as _audit, new_correlation_id as _corr
except Exception:
    _audit = None
    _corr = (lambda: "")
try:
    from skills.admin.emergency_stop import is_stopped
except Exception:
    def is_stopped() -> bool:            # type: ignore[misc]
        return False

ACTIONS = {
    "analyze": "workspace.analyze",
    "logs": "logs.scan",
    "tests": "devtools.run_tests",
    "backup": "workspace.backup",
    "backups": "workspace.analyze",
}


def _fmt_analyze(r: dict) -> str:
    if not r.get("allowed"):
        return f"⛔ Analisa repo ditolak: {r.get('reason', '')}"
    langs = sorted(r.get("languages", {}).items(), key=lambda kv: -kv[1])[:6]
    lang_s = ", ".join(f"{_wd.LANG_MAP.get(e, e)} {n}" for e, n in langs) or "—"
    dirs = sorted(r.get("top_dirs", {}).items(), key=lambda kv: -kv[1])[:8]
    dir_s = ", ".join(d for d, _ in dirs) or "—"
    lines = [
        f"📦 REPO {_wd.Path(r['root']).name}",
        f"File    : {r.get('total_files', 0)} ({r.get('size_mb', 0)} MB)",
        f"Bahasa  : {lang_s}",
        f"Folder  : {dir_s}",
        f"Entry   : {', '.join(r.get('entry_points', [])) or '—'}",
        f"TODO    : {r.get('todos', 0)} penanda",
    ]
    big = r.get("largest") or []
    if big:
        lines.append("Terbesar : " + "; ".join(f"{p.split(chr(92))[-1]} ({m} MB)"
                                              for m, p in big[:4]))
    return "\n".join(lines)


def _fmt_logs(r: dict) -> str:
    if not r.get("allowed"):
        return f"⛔ Scan log ditolak: {r.get('reason', '')}"
    if not r.get("exists"):
        return f"📜 LOG: {r.get('note', 'kosong')}"
    lines = [f"📜 LOG {r.get('pattern', '')} — {r.get('total', 0)} baris cocok, "
             f"{r.get('errors', 0)} error/deny"]
    lines.extend(f"  • {x}" for x in r.get("recent", []))
    return "\n".join(lines)


def _fmt_tests(r: dict) -> str:
    if not r.get("allowed"):
        return f"⛔ Run tests ditolak: {r.get('reason', '')}"
    mark = "✅ LOLOS" if r.get("ok") else "❌ GAGAL"
    return (f"🧪 TESTS ({r.get('runner')}) → {mark} "
            f"rc={r.get('returncode')} ({r.get('duration')}s)\n"
            f"{r.get('output', '')}")


def _fmt_backup(r: dict) -> str:
    if not r.get("allowed"):
        return f"⛔ Backup ditolak: {r.get('reason', '')}"
    if not r.get("ok"):
        return f"⛔ Backup DITOLAK: {r.get('refused', '')}"
    if r.get("dry_run"):
        return (f"💾 BACKUP (dry-run): {r.get('files', 0)} file, "
                f"{round(r.get('bytes', 0) / 1_048_576, 2)} MB → {r.get('dest')}\n"
                f"Tidak ada file ditulis. Untuk simpan sungguhan: confirm=true")
    return (f"💾 BACKUP tersimpan: {r.get('dest')} "
            f"({r.get('size_mb', 0)} MB, {r.get('files', 0)} file)")


def _fmt_backups(rows: list) -> str:
    if not rows:
        return "🗂️ DAFTAR BACKUP: belum ada backup."
    lines = [f"🗂️ DAFTAR BACKUP: {len(rows)} arsip"]
    lines.extend(f"  • {r['name']} — {r['size_mb']} MB ({r['modified']})"
                 for r in rows[:10])
    return "\n".join(lines)


def workspace_dev(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "analyze").lower().strip()
    target = str(p.get("target") or "").strip()
    pattern = str(p.get("pattern") or "").strip()
    confirm = bool(p.get("confirm"))

    try:
        if cmd not in ACTIONS:
            return ("cmd tidak dikenal. Gunakan: analyze | logs | tests | "
                    "backup | backups")
        # 1) Emergency stop
        if is_stopped():
            return ("⛔ EMERGENCY STOP aktif — semua eksekusi diblokir. "
                    "Ucapkan 'resume' untuk menonaktifkan.")
        # 2) Policy gate
        if _decide is not None:
            d = _decide(ACTIONS[cmd], target=target)
            if d.get("decision") == "deny":
                if _audit:
                    _audit({"skill": "workspace_dev", "action": ACTIONS[cmd],
                            "target": target[:120], "decision": "deny",
                            "risk_level": d.get("risk", ""), "result": "denied"})
                return (f"⛔ Perintah '{cmd}' DITOLAK policy: "
                        f"{d.get('reason', '')}")
            if d.get("decision") == "confirm" and not confirm:
                if _audit:
                    _audit({"skill": "workspace_dev", "action": ACTIONS[cmd],
                            "target": target[:120], "decision": "confirm",
                            "risk_level": d.get("risk", ""),
                            "result": "awaiting_confirmation"})
                return (f"⚠️ '{cmd}' butuh konfirmasi. Panggil ulang dengan "
                        f"confirm=true.")
        # 3) Audit + eksekusi
        if cmd == "analyze":
            out = _fmt_analyze(_wd.analyze_repo(target))
        elif cmd == "logs":
            out = _fmt_logs(_wd.scan_logs(target, pattern))
        elif cmd == "tests":
            out = _fmt_tests(_wd.run_tests(target))
        elif cmd == "backup":
            out = _fmt_backup(_wd.backup_workspace(target, dry_run=not confirm))
        else:
            out = _fmt_backups(_wd.list_backups())
        if _audit:
            _audit({"skill": "workspace_dev", "action": ACTIONS[cmd],
                    "target": (target or cmd)[:120], "decision": "allow",
                    "risk_level": "medium" if cmd in ("tests", "backup") else "low",
                    "result": "success", "correlation_id": _corr()})
        return out
    except Exception as e:
        return f"workspace_dev gagal: {e}"


TOOL = {
    "name": "workspace_dev",
    "description": (
        "Perkakas developer untuk workspace: analyze (peta repo: bahasa, "
        "ukuran, TODO), logs (scan audit/log untuk error & pola), tests "
        "(jalankan pytest/unittest di folder), backup (arsip ZIP, dry-run "
        "default), backups (daftar arsip). Semua dibatasi di dalam workspace."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "analyze | logs | tests | backup | backups"},
            "target": {"type": "STRING",
                       "description": "Subfolder dalam workspace (mis. 'core')"},
            "pattern": {"type": "STRING",
                        "description": "Filter teks untuk cmd=logs (mis. 'deny')"},
            "confirm": {"type": "BOOLEAN",
                        "description": "true untuk backup sungguhan (tulis zip)"},
        },
        "required": [],
    },
    "handler": workspace_dev,
}
