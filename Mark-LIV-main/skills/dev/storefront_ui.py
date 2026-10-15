"""
Storefront UI skill for Mark-LIV (Neira).

Local copy of https://github.com/vuestorefront/storefront-ui cloned at
scratch/storefront-ui. Lets Neira list / search / read the component source
and copy-paste block (showcase) examples for Vue (Nuxt) and React (Next).

Auto-discovered by core/action_loader.py and core/skill_hub.py via the TOOL dict.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


_BASE = _base_dir()
_REPO = _BASE / "scratch" / "storefront-ui"
_VUE_COMP = _REPO / "packages" / "sfui" / "frameworks" / "vue" / "components"
_REACT_COMP = _REPO / "packages" / "sfui" / "frameworks" / "react" / "components"
_VUE_BLOCKS = _REPO / "apps" / "preview" / "nuxt" / "pages" / "showcases"
_REACT_BLOCKS = _REPO / "apps" / "preview" / "next" / "pages" / "showcases"
_DOCS = _REPO / "apps" / "docs" / "components" / "content"

_MAX_CODE = 12000  # chars returned per read


def _repo_ok() -> str:
    if not _REPO.exists():
        return (
            f"Storefront UI repo belum ada di {_REPO}. "
            "Jalankan: git clone --depth 1 https://github.com/vuestorefront/storefront-ui.git "
            "scratch/storefront-ui"
        )
    return ""


def _framework_dirs(framework: str) -> Path:
    return _VUE_COMP if framework == "vue" else _REACT_COMP


def _list_components(framework: str) -> str:
    root = _framework_dirs(framework)
    if not root.exists():
        return f"Folder komponen tidak ditemukan: {root}"
    names = sorted(p.name for p in root.iterdir() if p.is_dir())
    return (
        f"[Storefront UI · {framework}] {len(names)} base components di {root}:\n"
        + ", ".join(names)
    )


def _search(query: str, framework: str) -> str:
    """Case-insensitive name match across components + blocks for both frameworks."""
    q = query.lower()
    hits: list[str] = []
    for fw, croot, brow in (
        ("vue", _VUE_COMP, _VUE_BLOCKS),
        ("react", _REACT_COMP, _REACT_BLOCKS),
    ):
        if framework not in ("all", fw):
            continue
        if croot.exists():
            for p in sorted(croot.iterdir()):
                if p.is_dir() and q in p.name.lower():
                    hits.append(f"component[{fw}] {p.name}")
        if brow.exists():
            for p in sorted(brow.iterdir()):
                if p.is_dir() and q in p.name.lower():
                    hits.append(f"block[{fw}] {p.name}")
    if not hits:
        return f"Tidak ada hasil untuk '{query}'. Coba kata kunci lain (mis.: card, checkout, modal)."
    return f"[Storefront UI] Hasil '{query}':\n- " + "\n- ".join(sorted(set(hits)))


def _read_component(name: str, framework: str) -> str:
    root = _framework_dirs(framework)
    comp = root / name
    if not comp.exists():
        # tolerate case / Sf-prefix mismatch
        matches = [p for p in root.iterdir() if p.is_dir() and name.lower() in p.name.lower()] \
            if root.exists() else []
        if len(matches) == 1:
            comp = matches[0]
        else:
            return (
                f"Komponen '{name}' tidak ditemukan di {root}. "
                "Pakai action='list' atau action='search' dulu."
            )
    files = [p for p in sorted(comp.rglob("*"))
             if p.is_file() and p.suffix in (".vue", ".tsx", ".ts", ".md")]
    if not files:
        return f"Tidak ada file kode di {comp}"
    out: list[str] = []
    total = 0
    for f in files:
        rel = f.relative_to(_REPO)
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            out.append(f"--- {rel}: gagal dibaca ({e})")
            continue
        if total + len(text) > _MAX_CODE:
            text = text[: max(0, _MAX_CODE - total)] + "\n... (dipotong)"
        total += len(text)
        out.append(f"--- {rel} ---\n{text}")
        if total >= _MAX_CODE:
            break
    return f"[Storefront UI · {framework}] {comp.name}:\n" + "\n\n".join(out)


def _read_block(name: str, framework: str) -> str:
    """Read a copy-paste showcase/block example (e.g. ProductCard, Checkout)."""
    brow = _VUE_BLOCKS if framework == "vue" else _REACT_BLOCKS
    if not brow.exists():
        return f"Folder block tidak ditemukan: {brow}"
    suffix = ".vue" if framework == "vue" else ".tsx"
    blk = brow / name
    if not blk.exists():
        matches = [p for p in brow.iterdir() if p.is_dir() and name.lower() in p.name.lower()]
        if len(matches) == 1:
            blk = matches[0]
        else:
            # fallback: match nama file individual, mis. ProductCardVertical.vue
            file_hits = [p for p in sorted(brow.rglob(f"*{suffix}"))
                         if p.is_file() and name.lower() in p.stem.lower()]
            if not file_hits:
                return (
                    f"Block '{name}' tidak ditemukan di {brow}. "
                    "Cek daftar dengan action='search' (hasil 'block[...]')."
                )
            files, blk = file_hits, file_hits[0].parent
            return _emit_files(files, f"[Storefront UI · {framework} block] {blk.name}")
    files = [p for p in sorted(blk.rglob(f"*{suffix}")) if p.is_file()]
    if not files:
        return f"Tidak ada file {suffix} di {blk}"
    return _emit_files(files, f"[Storefront UI · {framework} block] {blk.name}")


def _emit_files(files, header: str) -> str:
    out: list[str] = []
    total = 0
    for f in files:
        rel = f.relative_to(_REPO)
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            out.append(f"--- {rel}: gagal dibaca ({e})")
            continue
        if total + len(text) > _MAX_CODE:
            text = text[: max(0, _MAX_CODE - total)] + "\n... (dipotong)"
        total += len(text)
        out.append(f"--- {rel} ---\n{text}")
        if total >= _MAX_CODE:
            break
    return header + ":\n" + "\n\n".join(out)


def _list_blocks(framework: str) -> str:
    brow = _VUE_BLOCKS if framework == "vue" else _REACT_BLOCKS
    if not brow.exists():
        return f"Folder block tidak ditemukan: {brow}"
    names = sorted(p.name for p in brow.iterdir() if p.is_dir())
    return (
        f"[Storefront UI · {framework}] {len(names)} blocks/showcases di {brow}:\n"
        + ", ".join(names)
    )


def storefront_ui(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """
    Browse the local Storefront UI (Vue/React) library clone: list components,
    search by keyword, or read component / block source code for copy-paste.
    """
    p = parameters or {}
    action = str(p.get("action", "search")).strip().lower()
    query = str(p.get("query", "")).strip()
    framework = str(p.get("framework", "vue")).strip().lower()
    if framework not in ("vue", "react", "all"):
        framework = "vue"

    guard = _repo_ok()
    if guard:
        return guard

    try:
        if action == "list":
            if framework == "all":
                return _list_components("vue") + "\n\n" + _list_components("react")
            return _list_components(framework)

        if action == "list_blocks":
            if framework == "all":
                return _list_blocks("vue") + "\n\n" + _list_blocks("react")
            return _list_blocks(framework)

        if action == "search":
            if not query:
                return "Butuh 'query' untuk search (mis.: card, checkout, modal)."
            return _search(query, framework)

        if action == "component":
            if not query:
                return "Butuh 'query' = nama komponen (mis.: SfButton, modal)."
            if framework == "all":
                return (_read_component(query, "vue")
                        + "\n\n" + _read_component(query, "react"))
            return _read_component(query, framework)

        if action == "block":
            if not query:
                return "Butuh 'query' = nama block (mis.: ProductCard, Checkout)."
            if framework == "all":
                return (_read_block(query, "vue")
                        + "\n\n" + _read_block(query, "react"))
            return _read_block(query, framework)

        return (
            "Aksi tidak dikenal. Pilihan action: list | list_blocks | search | "
            "component | block (param opsional: query, framework=vue|react|all)."
        )
    except Exception as e:
        return f"Storefront UI skill error: {e}"


TOOL: Dict[str, Any] = {
    "name": "storefront_ui",
    "description": (
        "Browse the local Storefront UI clone (vuestorefront/storefront-ui): list or "
        "search e-commerce components (SfButton, SfModal, ...) and blocks (ProductCard, "
        "Checkout), and return copy-pasteable source code for Vue/Nuxt or React/Next."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "list = daftar base components; list_blocks = daftar blocks/showcases; "
                    "search = cari dengan query; component = baca source komponen; "
                    "block = baca contoh block siap pakai."
                ),
                "enum": ["list", "list_blocks", "search", "component", "block"],
            },
            "query": {
                "type": "STRING",
                "description": "Kata kunci / nama (mis.: SfButton, card, ProductCard). Wajib utk search/component/block.",
            },
            "framework": {
                "type": "STRING",
                "description": "Target framework: vue (default), react, atau all.",
                "enum": ["vue", "react", "all"],
            },
        },
        "required": ["action"],
    },
    "handler": storefront_ui,
    "behavior": "NON_BLOCKING",
}
