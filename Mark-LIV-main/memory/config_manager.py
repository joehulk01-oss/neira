import json
import os
import sys
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR    = get_base_dir()
CONFIG_DIR  = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "api_keys.json"

def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def config_exists() -> bool:
    return CONFIG_FILE.exists()

def save_api_keys(gemini_api_key: str) -> None:
    sync_all_configs({"gemini_api_key": gemini_api_key.strip()})


def sync_all_configs(updates: dict) -> dict:
    """
    Central sync function for Mark-LIV and Hermes settings.
    Updates config/api_keys.json, shared/config.env, and hermes-agent/.env.
    Ensures that when Apply/Save is clicked, EVERYTHING is saved and synced.
    """
    ensure_config_dir()
    data = load_api_keys()
    
    # Merge updates
    for k, v in updates.items():
        if v is not None:
            data[k] = str(v).strip() if isinstance(v, str) else v

    # 1. Save config/api_keys.json
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")

    # 2. Sync to shared/config.env
    env_path = BASE_DIR / "shared" / "config.env"
    env_dict = {}
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    ek, ev = s.split("=", 1)
                    env_dict[ek.strip()] = ev.strip()
        except Exception:
            pass

    if "gemini_api_key" in data:
        env_dict["GEMINI_API_KEY"] = data["gemini_api_key"] or ""
    if "vansrouter_url" in data:
        env_dict["VANSROUTER_URL"] = data["vansrouter_url"] or "http://127.0.0.1:20128"
    if "vansrouter_model" in data:
        env_dict["VANSROUTER_MODEL"] = data["vansrouter_model"] or "ag/gemini-3.8-flash-medium"
    if "user_name" in data:
        env_dict["USER_NAME"] = data["user_name"] or ""
    if "assistant_name" in data:
        env_dict["ASSISTANT_NAME"] = data["assistant_name"] or "Neira"

    gemini_k = env_dict.get('GEMINI_API_KEY', '')
    router_u = env_dict.get('VANSROUTER_URL', 'http://127.0.0.1:20128')
    router_m = env_dict.get('VANSROUTER_MODEL', 'ag/gemini-3.8-flash-medium')
    asst_n   = env_dict.get('ASSISTANT_NAME', 'Neira')
    usr_n    = env_dict.get('USER_NAME', '')
    # Neira Gateway — PERTAHANKAN nilai yang sudah ada (jangan sampai terhapus
    # tiap Apply/Save). {LAN_IP} = placeholder dinamis, jangan hardcode IP.
    gw_url   = env_dict.get('GATEWAY_URL', '') or 'https://{LAN_IP}:8000'
    gw_token = env_dict.get('GATEWAY_TOKEN', '') or 'lokal-uji-token'
    gw_auto  = env_dict.get('AUTOSTART_LOCAL_GATEWAY', 'true') or 'true'

    new_env_content = (
        "# ========================================\n"
        "# JARVIS HYBRID - CENTRAL CONFIGURATION\n"
        "# ========================================\n\n"
        "# API Keys & Endpoints\n"
        f"GEMINI_API_KEY={gemini_k}\n"
        f"GOOGLE_API_KEY={gemini_k}\n"
        f"VANSROUTER_URL={router_u}\n"
        f"OPENAI_BASE_URL={router_u}\n"
        f"VANSROUTER_MODEL={router_m}\n"
        f"HERMES_API_KEY={env_dict.get('HERMES_API_KEY', 'test')}\n"
        f"OPENAI_API_KEY={env_dict.get('HERMES_API_KEY', 'test')}\n\n"
        "# Browser Agent (jev-ultrafast)\n"
        f"TYPESAFE_API_KEY={env_dict.get('TYPESAFE_API_KEY', '')}\n"
        f"TYPESAFE_MODEL={env_dict.get('TYPESAFE_MODEL', 'jev-latest')}\n"
        f"TEXT_MODEL_API_KEY={env_dict.get('TEXT_MODEL_API_KEY', '')}\n"
        f"TEXT_MODEL_BASE_URL={env_dict.get('TEXT_MODEL_BASE_URL', 'https://openrouter.ai/api/v1')}\n"
        f"TEXT_MODEL={env_dict.get('TEXT_MODEL', 'inception/mercury-2.5')}\n"
        f"TEXT_MODEL_REASONING={env_dict.get('TEXT_MODEL_REASONING', 'none')}\n\n"
        "# Assistant Settings\n"
        f"USER_NAME={usr_n}\n"
        f"ASSISTANT_NAME={asst_n}\n"
        f"ROUTER_THRESHOLD={env_dict.get('ROUTER_THRESHOLD', '5')}\n"
        f"DEFAULT_VOICE={env_dict.get('DEFAULT_VOICE', 'id-ID-ArdiNeural')}\n"
        f"LANGUAGE={env_dict.get('LANGUAGE', 'id-ID')}\n"
        f"AUTO_LEARN=true\n"
        f"LOG_LEVEL=INFO\n\n"
        "# Neira Gateway (mode remote; {LAN_IP} = IP LAN aktif, terdeteksi otomatis)\n"
        f"GATEWAY_URL={gw_url}\n"
        f"GATEWAY_TOKEN={gw_token}\n"
        f"AUTOSTART_LOCAL_GATEWAY={gw_auto}\n"
    )
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(new_env_content, encoding="utf-8")
    except Exception:
        pass

    # 3. Sync to hermes-agent/.env and ~/.hermes/.env
    try:
        hermes_env = BASE_DIR / "hermes-agent" / ".env"
        hermes_env.parent.mkdir(parents=True, exist_ok=True)
        hermes_env.write_text(new_env_content, encoding="utf-8")
    except Exception:
        pass

    try:
        user_hermes_dir = Path.home() / ".hermes"
        if user_hermes_dir.exists():
            (user_hermes_dir / ".env").write_text(new_env_content, encoding="utf-8")
    except Exception:
        pass

    # Update runtime process environment
    if gemini_k:
        os.environ["GEMINI_API_KEY"] = gemini_k
        os.environ["GOOGLE_API_KEY"] = gemini_k
    if router_u:
        os.environ["VANSROUTER_URL"] = router_u
        os.environ["OPENAI_BASE_URL"] = router_u
    if router_m:
        os.environ["VANSROUTER_MODEL"] = router_m
        os.environ["DEEPSEEK_MODEL"] = router_m
    for _k in ("TYPESAFE_API_KEY", "TYPESAFE_MODEL", "TEXT_MODEL_API_KEY",
               "TEXT_MODEL_BASE_URL", "TEXT_MODEL", "TEXT_MODEL_REASONING"):
        if env_dict.get(_k):
            os.environ[_k] = env_dict[_k]

    # 4. Sync to shared/memory/user_preferences.json
    try:
        pref_path = BASE_DIR / "shared" / "memory" / "user_preferences.json"
        if pref_path.exists():
            pref = json.loads(pref_path.read_text(encoding="utf-8"))
            if "user_name" in data:
                pref["user_name"] = data["user_name"]
            pref_path.write_text(json.dumps(pref, indent=2), encoding="utf-8")
    except Exception:
        pass

    return data

def load_api_keys() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Failed to load api_keys.json: {e}")
        return {}

def get_gemini_key() -> str | None:
    return load_api_keys().get("gemini_api_key")

def is_configured() -> bool:
    key = get_gemini_key()
    return bool(key and len(key) > 15)


def get_assistant_name() -> str:
    """Return the configured assistant name, or 'JARVIS' if not set."""
    return load_api_keys().get("assistant_name", "JARVIS") or "JARVIS"


def get_user_name() -> str:
    """Return the configured user name for addressing."""
    return load_api_keys().get("user_name", "")


def save_assistant_config(assistant_name: str, user_name: str) -> None:
    """Persist assistant name and user name to config."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["assistant_name"] = assistant_name.strip() or "JARVIS"
    data["user_name"] = user_name.strip()
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


# ── Assistant voice ──────────────────────────────────────────────────────────
# Gemini Live prebuilt voices. Names are proper nouns — identical in every
# language, so this list is safe to show verbatim in any locale.
AVAILABLE_VOICES = ["Charon", "Puck", "Kore", "Fenrir", "Aoede"]
DEFAULT_VOICE    = "Charon"


def get_voice() -> str:
    """Return the configured Live voice, falling back to the default if unset
    or if the stored value is not a voice we recognise."""
    v = load_api_keys().get("voice_name", DEFAULT_VOICE) or DEFAULT_VOICE
    return v if v in AVAILABLE_VOICES else DEFAULT_VOICE


def save_voice(voice_name: str) -> None:
    """Persist the chosen Live voice. Unknown names collapse to the default so a
    bad value can never reach the API and break the session."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    v = (voice_name or "").strip()
    data["voice_name"] = v if v in AVAILABLE_VOICES else DEFAULT_VOICE
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_wake_word_enabled() -> bool:
    """Whether local wake-word gating is on (assistant sleeps until 'Hey Jarvis')."""
    return load_api_keys().get("wake_word_enabled", False)


def save_wake_word_enabled(enabled: bool) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["wake_word_enabled"] = bool(enabled)
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_push_to_talk_enabled() -> bool:
    """Hold-a-key-to-speak. When on, the mic is closed unless the chord is held."""
    return load_api_keys().get("push_to_talk_enabled", False)


def save_push_to_talk_enabled(enabled: bool) -> None:
    _save_flag("push_to_talk_enabled", enabled)


HUD_STYLES = ("face", "core")


def get_hud_style() -> str:
    """Which centrepiece the HUD draws: the animated head, or the reactor core.

    Taste, not capability — both render in the same software painter and cost
    about the same. Defaults to the head because that is what MARK LIV shipped
    with; anyone who preferred the older look can switch back in ⚙ and the
    choice survives a restart.
    """
    v = str(load_api_keys().get("hud_style", "face")).strip().lower()
    return v if v in HUD_STYLES else "face"


def save_hud_style(style: str) -> None:
    s = str(style or "").strip().lower()
    _save_flag("hud_style", s if s in HUD_STYLES else "face")


REACTOR_STYLES = ("classic", "quantum", "glsl", "web3d")


def get_reactor_style() -> str:
    """Which reactor engine draws the HUD core when hud_style == "core".

    classic — the original 2D painter rings; quantum — faux-3D ring stack with
    orbital particles (no extra deps); glsl — GPU raymarch (needs QtOpenGLWidgets);
    web3d — three.js + bloom (needs PyQt6-WebEngine). The choice survives a
    restart and degrades gracefully if the chosen engine is unavailable.
    """
    v = str(load_api_keys().get("reactor_style", "quantum")).strip().lower()
    return v if v in REACTOR_STYLES else "quantum"


def save_reactor_style(style: str) -> None:
    s = str(style or "").strip().lower()
    _save_flag("reactor_style", s if s in REACTOR_STYLES else "quantum")


# ── Live-session tuning ──────────────────────────────────────────────────────
# Everything here is optional and has a working default, so an untouched
# config behaves exactly like a configured one. Each value is also a way out:
# if a future model dislikes one of these, set it back and nothing else changes.

def get_thinking_enabled() -> bool:
    """Whether the Live model may spend tokens thinking before it answers.

    Off by default. A voice assistant is judged on how fast it starts talking,
    and the reasoning that actually needs deliberation in this app is delegated
    to the planning tools, which run on a separate non-Live model.
    """
    return bool(load_api_keys().get("thinking_enabled", False))


def save_thinking_enabled(enabled: bool) -> None:
    _save_flag("thinking_enabled", enabled)


def get_turn_tuning() -> dict:
    """How eagerly the server decides you have stopped speaking.

    OFF by default, and that default was earned. Cutting turns shorter looks
    like a free speed win and is not: proactive audio has to judge whether an
    utterance was even addressed to the assistant, and a turn clipped early
    gives it less to judge, so it stays quiet — and the reply to your first
    sentence only arrives once your second one has given it enough context.
    That reads as the assistant being a turn behind, which is far worse than
    the fraction of a second the tuning saves.

    Turn it on with "turn_tuning": {"enabled": true} if your own microphone and
    speaking pace suit it. `silence_ms` is the one that is felt: the pause the
    server sits through before accepting your turn is over.
    """
    cfg = load_api_keys().get("turn_tuning")
    cfg = cfg if isinstance(cfg, dict) else {}

    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, int(cfg.get(key, default))))
        except (TypeError, ValueError):
            return default

    return {
        "enabled":    bool(cfg.get("enabled", False)),
        "silence_ms": _int("silence_ms", 550, 200, 3000),
        "prefix_ms":  _int("prefix_ms", 150, 0, 1000),
        # "high" = quicker to decide speech has ended.
        "end_sensitivity":   str(cfg.get("end_sensitivity", "high")).lower(),
        "start_sensitivity": str(cfg.get("start_sensitivity", "default")).lower(),
    }


def save_turn_tuning(values: dict) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    cur = data.get("turn_tuning")
    cur = dict(cur) if isinstance(cur, dict) else {}
    cur.update(values or {})
    data["turn_tuning"] = cur
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_proactive_audio_enabled() -> bool:
    """Whether the model gets to decide an utterance was not aimed at it and
    stay quiet.

    On by default — it is what stops the assistant answering the room. But it
    is also the first thing to switch off if replies ever seem to arrive a turn
    late: what looks like lag is usually the model having judged your previous
    sentence as not addressed to it, and only changing its mind once the next
    one arrives.
    """
    return bool(load_api_keys().get("proactive_audio", True))


def save_proactive_audio_enabled(enabled: bool) -> None:
    _save_flag("proactive_audio", enabled)


MEDIA_RESOLUTIONS = ("default", "low", "medium", "high")


def get_media_resolution() -> str:
    """How finely the model tokenises the screenshots and camera frames it is
    sent. 'medium' keeps on-screen text readable at a fraction of the tokens a
    full-resolution frame costs; 'low' is cheaper still but starts losing small
    text, which is most of what screen captures are for."""
    v = str(load_api_keys().get("media_resolution", "medium")).strip().lower()
    return v if v in MEDIA_RESOLUTIONS else "medium"


def save_media_resolution(value: str) -> None:
    v = str(value or "").strip().lower()
    _save_flag("media_resolution", v if v in MEDIA_RESOLUTIONS else "medium")


def _save_flag(key: str, value) -> None:
    """Read-modify-write one key without disturbing the rest of the config."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[key] = bool(value) if isinstance(value, bool) else value
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_brief_enabled() -> bool:
    return load_api_keys().get("morning_brief_enabled", True)


def save_brief_enabled(enabled: bool) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["morning_brief_enabled"] = enabled
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


# ── Audio devices ────────────────────────────────────────────────────────────
# Stored as device NAMES, not sounddevice indices. Indices shift every time a
# USB device is plugged in or removed, so a saved index silently starts pointing
# at a different microphone. The empty string means "system default", which is
# both the factory setting and what an unresolvable saved device falls back to —
# so unplugging a headset degrades to the built-in speakers instead of crashing.

def _patch_config(**fields) -> None:
    """Read-modify-write one or more keys in api_keys.json.

    Every setter in this file open-coded this. Collapsing it here means a new
    setting is one line, and there is one place where a corrupt config file is
    handled instead of nine."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data.update(fields)
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_input_device() -> str:
    """Microphone device name, or '' for the system default."""
    return (load_api_keys().get("input_device", "") or "").strip()


def save_input_device(name: str) -> None:
    _patch_config(input_device=(name or "").strip())


def get_output_device() -> str:
    """Speaker device name, or '' for the system default."""
    return (load_api_keys().get("output_device", "") or "").strip()


def save_output_device(name: str) -> None:
    _patch_config(output_device=(name or "").strip())


def get_plugin_enabled(plugin_name: str) -> bool:
    """Plugins are enabled by default the moment they're discovered (opt-out model)."""
    return load_api_keys().get("plugins_enabled", {}).get(plugin_name, True)


# ── Per-plugin settings ("tokens" / connection details) ───────────────────────
# Generic store so a plugin can declare its own config fields (PLUGIN_SETTINGS)
# and the settings UI renders + persists them WITHOUT any core edit — keeping the
# drop-in model intact. Values live under plugin_config[<namespace>][<key>].
# A namespace defaults to the plugin name, but a suite of plugins (e.g. the
# several printer plugins) can share ONE namespace.
def get_plugin_config(namespace: str) -> dict:
    """All stored values for a namespace (empty dict if none set yet)."""
    cfg = load_api_keys().get("plugin_config")
    val = cfg.get(namespace) if isinstance(cfg, dict) else None
    return dict(val) if isinstance(val, dict) else {}


def get_plugin_setting(namespace: str, key: str, default=None):
    """A single value from a namespace, or `default` if unset."""
    return get_plugin_config(namespace).get(key, default)


def save_plugin_config(namespace: str, values: dict) -> None:
    """Merge `values` into a namespace's stored config (read-modify-write, like
    every other helper here). Only the provided keys are touched."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    pc = data.get("plugin_config")
    if not isinstance(pc, dict):
        pc = {}
    cur = pc.get(namespace)
    if not isinstance(cur, dict):
        cur = {}
    cur.update(values)
    pc[namespace] = cur
    data["plugin_config"] = pc
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def save_plugin_enabled(plugin_name: str, enabled: bool) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    plugins_cfg = data.get("plugins_enabled")
    if not isinstance(plugins_cfg, dict):
        plugins_cfg = {}
    plugins_cfg[plugin_name] = enabled
    data["plugins_enabled"] = plugins_cfg
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")