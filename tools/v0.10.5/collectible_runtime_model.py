"""Pure fail-closed model for researched collectible families."""
from __future__ import annotations


def normalize_uid(value) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return f"{value & 0xFFFFFFFFFFFFFFFF:016X}"
    if isinstance(value, str):
        text = value.strip()
        try:
            if text.lower().startswith("0x"):
                return f"{int(text, 16) & 0xFFFFFFFFFFFFFFFF:016X}"
            if text.isdigit():
                return f"{int(text, 10) & 0xFFFFFFFFFFFFFFFF:016X}"
            if len(text) == 16 and all(char in "0123456789abcdefABCDEF" for char in text):
                return text.upper()
        except ValueError:
            return None
    return None


class CollectibleRuntimeModel:
    """UI oracle. Unknown progression never creates a marker."""

    def __init__(self, catalogue: dict):
        self.rows = {row["catalogue_id"]: row for row in catalogue["collectibles"]}
        self.by_uid = {normalize_uid(row["marker"]["uid"]): row for row in self.rows.values()}
        self.state = {key: "unknown" for key in self.rows}
        self.map_open = False
        self.realm = None
        self.filters = set()
        self.map_icons = set()
        self.selection = None
        self.active_target = None
        self.retries = {}
        self.permanent_polling = False

    def _family_enabled(self, family: str) -> bool:
        return not self.filters or family in self.filters

    def _visible(self, key: str) -> bool:
        row = self.rows[key]
        if not self.map_open or row["realm"] != self.realm or not self._family_enabled(row["family"]):
            return False
        parent = row["progression"].get("parent_catalogue_id")
        if parent:
            if self.state.get(parent) != "remaining":
                return False
            if row["family"] == "nornir_seal":
                return self.state[key] == "remaining"
            return True
        return self.state[key] == "remaining"

    def _sync(self):
        self.map_icons = {key for key in self.rows if self._visible(key)}
        if self.selection not in self.map_icons:
            self.selection = None

    def open_map(self, realm: str, filters=()):
        self.map_open = True
        self.realm = realm
        self.filters = set(filters)
        self._sync()

    def teardown(self):
        self.map_open = False
        self.map_icons.clear()
        self.selection = None

    def observe(self, key: str, complete: bool):
        if key not in self.rows:
            raise KeyError(key)
        self.state[key] = "complete" if complete else "remaining"
        if complete and self.active_target == ("custom", key):
            self.active_target = None
        self._sync()

    def load_save(self):
        self.state = {key: "unknown" for key in self.rows}
        self.map_icons.clear()
        self.selection = None
        self.active_target = None
        self.retries.clear()

    def collide(self, key: str):
        if key not in self.map_icons:
            return None
        self.selection = key
        return key

    def click(self, uid) -> str:
        normalized = normalize_uid(uid)
        row = self.by_uid.get(normalized)
        if self.selection is None or row is None or row["catalogue_id"] != self.selection:
            self.selection = None
            return "delegate"
        key = self.selection
        self.selection = None
        if key not in self.map_icons:
            return "refused"
        target = ("custom", key)
        if self.active_target == target:
            self.active_target = None
            return "removed"
        self.active_target = target
        return "shown"

    def click_other(self, family: str, identity: str) -> str:
        self.selection = None
        target = (family, identity)
        if self.active_target == target:
            self.active_target = None
            return "removed"
        self.active_target = target
        return "shown"

    def retry(self, key: str, cap: int = 3) -> bool:
        count = self.retries.get(key, 0)
        if count >= cap:
            return False
        self.retries[key] = count + 1
        return True
