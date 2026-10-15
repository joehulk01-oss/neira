# policy_engine.py
"""
policy_engine.py — Safety gate for Neira actions (Blueprint Tahap 1).

Setiap aksi berisiko harus lewat sini SEBELUM dieksekusi:

    from core.policy_engine import decide
    d = decide("app.kill", target="csrss")
    → {"decision": "deny", "risk": "critical", "reason": "proses sistem kritikal"}

    d = decide("app.kill", target="chrome")
    → {"decision": "confirm", "risk": "high", ...}   # butuh konfirmasi user

    d = decide("app.close", target="chrome")
    → {"decision": "allow", "risk": "medium", ...}   # langsung eksekusi

Aturan dibaca dari policies/default_policy.json (bisa diedit tanpa restart —
mtime dipantau). Jika file hilang/rusak, pakai DEFAULTS bawaan kode — jadi
sistem tetap aman, tidak pernah "open by failure".

Filosofi (dari blueprint): model boleh MEMINTA apa saja; policy yang MEMUTUSKAN.
Deny diputuskan di sini, bukan di prompt — prompt bisa ditipu, file policy tidak.

Murni stdlib — tanpa PyYAML (policy pakai JSON), tanpa dependensi eksternal.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


def _base_dir() -> Path:
    try:
        from core.paths import BASE_DIR  # type: ignore
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
POLICY_PATH = BASE_DIR / "policies" / "default_policy.json"

# ── Bawaan aman (fallback jika policy file hilang) ───────────────────────────
DEFAULTS: dict[str, Any] = {
    "default_decision": "allow",        # aksi tak terdaftar → boleh, tapi dicatat
    "default_risk": "low",
    "confirm_risk_thresholds": {"high": "confirm", "critical": "deny"},
    "rules": {
        # aksi                            [risk, decision]
        "app.list":                     ["low", "allow"],
        "app.switch":                   ["low", "allow"],
        "app.open":                     ["low", "allow"],
        "app.close":                    ["medium", "allow"],
        "app.kill":                     ["high", "confirm"],
        "process.kill":                 ["critical", "deny"],
        "file.delete":                  ["high", "confirm"],
        "file.write_outside_workspace": ["high", "confirm"],
        "message.send":                 ["high", "confirm"],
        "settings.security_change":     ["critical", "deny"],
        "system.shutdown":              ["high", "confirm"],
        "system.restart":               ["high", "confirm"],
    },
    "protected_processes": [
        "system", "idle", "csrss", "wininit", "winlogon", "smss", "services",
        "lsass", "svchost", "registry", "memcompression", "memory compression",
        "dwm", "fontdrvhost", "windeploy",
    ],
}

_lock = threading.Lock()
_cache: dict[str, Any] = {"mtime": 0.0, "policy": dict(DEFAULTS)}


def load_policy(force: bool = False) -> dict[str, Any]:
    """Baca policy file (cache berdasarkan mtime). Return dict policy aktif."""
    with _lock:
        try:
            mtime = POLICY_PATH.stat().st_mtime
        except OSError:
            mtime = 0.0
        if force or mtime != _cache["mtime"]:
            policy = json.loads(json.dumps(DEFAULTS))   # deep copy
            if mtime and POLICY_PATH.exists():
                try:
                    with open(POLICY_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        for key in ("default_decision", "default_risk",
                                    "confirm_risk_thresholds", "rules",
                                    "protected_processes"):
                            if key in data:
                                policy[key] = data[key]
                except Exception:
                    pass                                # file rusak → pakai default
            _cache["policy"] = policy
            _cache["mtime"] = mtime
        return _cache["policy"]


def protected_processes() -> set[str]:
    """Nama proses (lowercase) yang TIDAK BOLEH dimatikan siapa pun."""
    return {p.lower() for p in load_policy().get("protected_processes", [])}


def decide(action: str, **params: Any) -> dict[str, Any]:
    """Putuskan satu aksi. Return: decision allow|confirm|deny, risk, reason.

    Urutan penilaian:
      1. Target = proses terproteksi → deny (critical) — selalu menang.
      2. Ada rule eksplisit untuk action → pakai risk+decision rule itu.
      3. Tidak ada rule → default_decision (dicatat sebagai unclassified).
    """
    policy = load_policy()
    target = str(params.get("target") or params.get("name") or "").strip().lower()
    if target.endswith(".exe"):
        target = target[:-4]

    if target and target in protected_processes():
        return {
            "decision": "deny", "risk": "critical",
            "reason": f"'{target}' adalah proses sistem kritikal — tidak boleh disentuh.",
            "rule": "protected_processes",
        }

    rules: dict = policy.get("rules", {})
    rule = rules.get(action)
    if rule is None:
        # wildcard sederhana: "app.*" cocok "app.close"
        prefix = action.split(".", 1)[0] + ".*"
        rule = rules.get(prefix)
    if rule and len(rule) >= 2:
        return {
            "decision": str(rule[1]).lower(),
            "risk": str(rule[0]).lower(),
            "reason": f"rule '{action}' → {rule[0]}/{rule[1]}",
            "rule": action,
        }

    return {
        "decision": str(policy.get("default_decision", "allow")).lower(),
        "risk": str(policy.get("default_risk", "low")).lower(),
        "reason": f"aksi '{action}' tidak terdaftar di policy (default)",
        "rule": None,
    }


def needs_confirmation(decision: dict[str, Any]) -> bool:
    return decision.get("decision") == "confirm"


def is_denied(decision: dict[str, Any]) -> bool:
    return decision.get("decision") == "deny"


def deny_message(decision: dict[str, Any], action: str, target: str = "") -> str:
    """Pesan tolakan siap-tampilk untuk model/user."""
    tgt = f" '{target}'" if target else ""
    return (f"❌ Ditolak oleh policy ({decision.get('risk', 'unknown')}): "
            f"aksi '{action}'{tgt} — {decision.get('reason', '')}")


def confirm_message(decision: dict[str, Any], action: str, target: str = "") -> str:
    """Pesan minta konfirmasi. Model harus bertanya dulu; eksekusi ulang
    dengan confirm=true HANYA setelah user menjawab ya."""
    tgt = f" '{target}'" if target else ""
    return (f"⚠️ Aksi berisiko {decision.get('risk', 'high')}: {action}{tgt}. "
            "Tanyakan dulu ke user ('mau dilanjutkan?'). Lanjutkan hanya jika "
            "user menjawab YA, lalu panggil ulang dengan confirm=true.")


def describe() -> str:
    """Ringkasan policy untuk prompt model / debug."""
    policy = load_policy()
    lines = ["NEIRA POLICY (aksi — risiko — keputusan):"]
    for act, (risk, dec) in sorted(policy.get("rules", {}).items()):
        lines.append(f"  {act:32s} {risk:9s} {dec}")
    return "\n".join(lines)
