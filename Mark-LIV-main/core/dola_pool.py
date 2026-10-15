"""
Dola Account Pool Manager.
Stores, rotates, and manages session cookies for Dola AI accounts.
Enables high-throughput / seamless rotation without running browser DOM.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
POOL_FILE = CONFIG_DIR / "dola_pool.json"


class DolaAccountPool:
    """Manages pool of Dola AI accounts and rotation."""

    def __init__(self, pool_file: Optional[Path] = None):
        self.pool_file = pool_file or POOL_FILE
        self._ensure_pool_file()

    def _ensure_pool_file(self) -> None:
        self.pool_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.pool_file.exists():
            default_data = {
                "accounts": [],
                "current_index": 0,
                "version": "1.0"
            }
            self._save(default_data)

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.pool_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"accounts": [], "current_index": 0, "version": "1.0"}

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.pool_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def list_accounts(self) -> List[Dict[str, Any]]:
        """Returns list of all accounts in the pool."""
        data = self._load()
        return data.get("accounts", [])

    def add_account(
        self,
        name: str,
        cookies: Dict[str, str],
        user_agent: str,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Adds a newly authenticated account to the pool."""
        data = self._load()
        accounts = data.get("accounts", [])

        if not account_id:
            # uuid pendek — timestamp dobel saat 2 akun ditambah pada detik yang
            # sama membuat id tabrakan (bug nyata yang tertangkap test_dola_chat).
            account_id = f"dola_{uuid.uuid4().hex[:10]}"

        # Check if already exists by sessionid or id
        session_id = cookies.get("sessionid", "")
        for acc in accounts:
            if session_id and acc.get("cookies", {}).get("sessionid") == session_id:
                # Update existing
                acc["name"] = name
                acc["cookies"] = cookies
                acc["user_agent"] = user_agent
                acc["status"] = "active"
                acc["updated_at"] = time.time()
                acc["error_count"] = 0
                self._save(data)
                return acc

        account_entry = {
            "id": account_id,
            "name": name,
            "created_at": time.time(),
            "updated_at": time.time(),
            "cookies": cookies,
            "user_agent": user_agent,
            "status": "active",
            "usage_count": 0,
            "last_used": None,
            "cooldown_until": 0,
            "error_count": 0
        }
        accounts.append(account_entry)
        data["accounts"] = accounts
        self._save(data)
        return account_entry

    def remove_account(self, account_id: str) -> bool:
        """Removes an account from pool."""
        data = self._load()
        accounts = data.get("accounts", [])
        new_accounts = [a for a in accounts if a.get("id") != account_id]
        if len(new_accounts) != len(accounts):
            data["accounts"] = new_accounts
            self._save(data)
            return True
        return False

    def get_active_account(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the next active account using round-robin rotation.
        Filters out accounts currently in cooldown.
        """
        data = self._load()
        accounts = data.get("accounts", [])
        if not accounts:
            return None

        now = time.time()
        # Find all available active accounts
        available = []
        for acc in accounts:
            if acc.get("status") == "active":
                cooldown_until = acc.get("cooldown_until", 0)
                if now >= cooldown_until:
                    available.append(acc)

        if not available:
            # All accounts in cooldown or disabled; return least recently used
            return min(accounts, key=lambda a: a.get("last_used") or 0)

        # Round robin over available
        cur_idx = data.get("current_index", 0) % len(available)
        selected = available[cur_idx]

        data["current_index"] = (cur_idx + 1) % len(available)
        self._save(data)
        return selected

    def report_usage(self, account_id: str, success: bool, error_msg: str = "") -> None:
        """Updates account health metrics after a request."""
        data = self._load()
        for acc in data.get("accounts", []):
            if acc.get("id") == account_id:
                acc["last_used"] = time.time()
                if success:
                    acc["usage_count"] = acc.get("usage_count", 0) + 1
                    acc["error_count"] = 0
                    acc["status"] = "active"
                else:
                    err_cnt = acc.get("error_count", 0) + 1
                    acc["error_count"] = err_cnt
                    # Cooldown for 3 minutes on error/rate limit
                    acc["cooldown_until"] = time.time() + 180
                    if err_cnt >= 5:
                        acc["status"] = "error"
                break
        self._save(data)


# Global instance
dola_pool = DolaAccountPool()
