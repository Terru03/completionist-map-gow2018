"""Pure model of catalogue-driven Raven map, routing, and lifecycle rules."""
from __future__ import annotations


class RavenRuntimeModel:
    """Test oracle. Unknown state is hidden and all ownership checks fail closed."""

    def __init__(self, catalogue: dict):
        self.rows = {row["catalogue_id"]: row for row in catalogue["ravens"]}
        self.by_uid = {row["marker"]["uid"]: row for row in catalogue["ravens"]}
        self.by_object = {f"object:{row['catalogue_id']}": row for row in catalogue["ravens"]}
        self.state = {key: "unknown" for key in self.rows}
        self.realm = None
        self.map_icons: set[str] = set()
        self.selection = None
        self.active_target = None
        self.map_open = False
        self.permanent_polling = False

    def set_realm(self, realm: str):
        self.realm = realm
        self._sync_icons()

    def open_map(self, realm: str):
        self.map_open = True
        self.realm = realm
        self._sync_icons()

    def teardown_map(self):
        self.map_open = False
        self.map_icons.clear()
        self.selection = None

    def observe(self, catalogue_id: str, collected: bool):
        if catalogue_id not in self.rows:
            raise KeyError(catalogue_id)
        self.state[catalogue_id] = "collected" if collected else "uncollected"
        if collected and self.active_target == ("raven", catalogue_id):
            self.active_target = None
        if collected and self.selection == catalogue_id:
            self.selection = None
        self._sync_icons()

    def restore(self, catalogue_id: str, collected: bool):
        self.observe(catalogue_id, collected)

    def load_save(self):
        self.state = {key: "unknown" for key in self.rows}
        self.map_icons.clear()
        self.selection = None
        self.active_target = None

    def _sync_icons(self):
        if not self.map_open:
            self.map_icons.clear()
            return
        self.map_icons = {
            key for key, row in self.rows.items()
            if row["realm"] == self.realm and self.state[key] == "uncollected"
        }

    def collide(self, object_token: str):
        row = self.by_object.get(object_token)
        if row is None or row["catalogue_id"] not in self.map_icons:
            self.selection = None
            return None
        self.selection = row["catalogue_id"]
        return self.selection

    def confirm_prompt(self, curr_marker_uid: str | None, legacy_proven_bridge: bool = False) -> bool:
        if self.selection is None:
            return False
        row = self.rows[self.selection]
        if curr_marker_uid == row["marker"]["uid"]:
            return True
        return bool(
            legacy_proven_bridge
            and curr_marker_uid is None
            and row["marker"]["name"] == "Completionist_V103_Veithurgard_Raven_01"
        )

    def click_raven(self, curr_marker_uid: str | None, legacy_proven_bridge: bool = False) -> str:
        if not self.confirm_prompt(curr_marker_uid, legacy_proven_bridge):
            self.selection = None
            return "delegate"
        catalogue_id = self.selection
        self.selection = None
        if self.state[catalogue_id] != "uncollected":
            return "refused"
        target = ("raven", catalogue_id)
        if self.active_target == target:
            self.active_target = None
            return "removed"
        self.active_target = target
        return "shown"

    def click_other(self, family: str, identity: str):
        self.selection = None
        target = (family, identity)
        if self.active_target == target:
            self.active_target = None
            return "removed"
        self.active_target = target
        return "shown"
