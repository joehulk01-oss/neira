# -*- coding: utf-8 -*-
"""Smoke test — SATU identitas "Neira".

Aturan role yang disepakati:
1. Hanya "Neira" yang terlihat ke user; "Hermes" = nama internal inti otak,
   tidak boleh bocor ke ucapan, label terminal, atau teks hasil tool.
2. Heavy task: konfirmasi 1 kalimat ("baik, saya kerjakan") -> inti otak kerja
   SENYAP (tanpa update berkala) -> lapor hasil pakai orang pertama "saya".
"""
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ok, fail = [], []


def check(name: str, cond: bool, extra: str = "") -> None:
    (ok if cond else fail).append(name)
    print(("PASS" if cond else "FAIL"), "-", name, ("" if cond else f"({extra})"))


# ── 1. Prompt Neira: satu identitas, tanpa entitas "Hermes"/"Mandor" ────────
print("== 1. prompt.txt identity ==")
prompt = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
stripped = prompt.replace('Never say "Hermes", ', "")
check("prompt never presents Hermes as an entity", "Hermes" not in stripped)
check("prompt has no Mandor framing", "Mandor" not in prompt)
check("prompt has no Tony hardcode", "Tony" not in prompt)
check("prompt declares ONE identity", "ONE identity" in prompt)
check("prompt frames deep core layer", "Deep core layer" in prompt)
check("prompt: confirm 1 sentence example", "baik, saya kerjakan" in prompt)
check("prompt: silent while core works", "no progress updates" in prompt)
check("prompt: report in first person", 'first person ("saya sudah memperbaiki' in prompt)
check("prompt keeps {skill_routing} token", "{skill_routing}" in prompt)
check("prompt keeps category-first rule", "Route by category first" in prompt)
check("prompt keeps butuh konten rule", "butuh konten" in prompt)

# ── 2. Prompt inti otak (hermes_connector): tidak perkenalkan diri terpisah ─
print("\n== 2. deep core prompt (hermes_connector) ==")
from router.hermes_connector import HermesConnector  # noqa: E402

src = inspect.getsource(HermesConnector.process_heavy_task)
check("core prompt not 'You are Hermes Agent'", "You are Hermes Agent" not in src)
check("core prompt framed as inner brain", "inner brain" in src)
check("core prompt bans self-naming", "'Hermes'" in src)
check("report_for_mark first person", "ORANG PERTAMA" in src and "'saya'" in src)
check("routing substrings intact (regression)",
      "KONTEN = content creation" in src and "ADMIN  = system, browser" in src)
check("shared-library wording intact (regression)", "SAME" in src and "Neira" in src)

# ── 3. deep_think: hasil & deskripsi tool bebas "Hermes" ───────────────────
print("\n== 3. deep_think ==")
from skills.dev.deep_think import deep_think, TOOL  # noqa: E402

dt_src = inspect.getsource(deep_think)
check("deep_think prompt not 'You are Hermes Agent'", "You are Hermes Agent" not in dt_src)
check("deep_think bans 'Hermes' name", "never say 'Hermes'" in dt_src)
check("deep_think report_for_mark first person", "ORANG PERTAMA" in dt_src)
check("deep_think result label clean",
      "[Status Eksekusi Hermes" not in dt_src and "[Status Eksekusi di Laptop]" in dt_src)
check("deep_think terminal title is Neira", 'title="Neira Terminal' in dt_src)
check("TOOL description free of Hermes", "Hermes" not in TOOL["description"])

# ── 4. Eksekutor & remediator: teks hasil (akan diucapkan) orang pertama ────
print("\n== 4. executor + remediator strings ==")
import core.hermes_executor as he  # noqa: E402

he_src = inspect.getsource(he)
check("executor default title Neira", 'title: str = "Neira Terminal"' in he_src)
check("executor no [HERMES] banner", "[HERMES" not in he_src)
check("executor register_skill msg clean", "Neira & Hermes" not in he_src)

import core.hermes_remediator as hr  # noqa: E402

hr_src = inspect.getsource(hr)
check("remediator reports first person", "Saya membuka" in hr_src and "Analisis saya" in hr_src)
check("remediator detail clean",
      "Hermes membuka" not in hr_src and "Analisis Hermes" not in hr_src
      and "Analisis Kegagalan Hermes" not in hr_src and "Hermes berhasil" not in hr_src)

# ── 5. Teks skill & label UI ───────────────────────────────────────────────
print("\n== 5. skill texts + UI labels ==")
ms = (ROOT / "skills" / "admin" / "manage_skills.py").read_text(encoding="utf-8")
check("manage_skills output clean", "Neira & Hermes" not in ms and "atau Hermes" not in ms)
check("manage_skills description clean", "you or Hermes" not in ms)
oa = (ROOT / "skills" / "admin" / "open_app.py").read_text(encoding="utf-8")
check("open_app result clean", "Hermes berhasil" not in oa)
ui = (ROOT / "ui.py").read_text(encoding="utf-8")
check("ui labels clean", "HERMES ·" not in ui and "Pilih Model Hermes" not in ui)
check("ui logs clean", "Hermes synced" not in ui and "synced to Hermes" not in ui)

print(f"\nPASS {len(ok)} FAIL {len(fail)}")
if fail:
    print("FAILED:", *fail, sep="\n  - ")
    sys.exit(1)
