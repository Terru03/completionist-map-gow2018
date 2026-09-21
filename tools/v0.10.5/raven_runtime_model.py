"""Pure model of catalogue-driven Raven map, routing, and lifecycle rules."""
from __future__ import annotations


class RavenRuntimeModel:
    """Test oracle. Catalogue Ravens show unless the current save confirms them collected."""

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
        self.last_native_generation: int | None = None
        self.authority_boundary_pending = False
        self.authority_boundary_generation: int | None = None

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

    def apply_persisted_kills(self, catalogue_ids) -> int:
        """Replace cached state with an authoritative persisted killed-Raven set."""
        self.state = {key: "unknown" for key in self.rows}
        accepted = 0
        for catalogue_id in catalogue_ids:
            if catalogue_id not in self.rows or self.state[catalogue_id] == "collected":
                continue
            self.state[catalogue_id] = "collected"
            accepted += 1
        if (
            self.active_target is not None
            and self.active_target[0] == "raven"
            and self.state.get(self.active_target[1]) == "collected"
        ):
            self.active_target = None
        if self.selection is not None and self.state.get(self.selection) == "collected":
            self.selection = None
        self._sync_icons()
        return accepted

    def apply_native_snapshot(self, generation: int, catalogue_ids) -> str:
        if generation < 1:
            return "invalid"
        if (
            self.authority_boundary_pending
            and self.authority_boundary_generation is not None
            and generation <= self.authority_boundary_generation
        ):
            return "boundary_wait"
        if self.last_native_generation is not None and generation <= self.last_native_generation:
            return "stale"
        self.apply_persisted_kills(catalogue_ids)
        self.last_native_generation = generation
        self.authority_boundary_pending = False
        self.authority_boundary_generation = None
        return "applied"

    def observe_event(self, catalogue_id: str, collected: bool) -> str:
        """Gameplay evidence may only add a kill; alive requires atomic authority."""
        if not collected:
            return "deferred"
        self.observe(catalogue_id, True)
        return "applied"

    def notify_load_boundary(self):
        """Keep last-good state until a strictly post-boundary snapshot arrives."""
        self.authority_boundary_pending = True
        self.authority_boundary_generation = self.last_native_generation
        self.selection = None
        self.active_target = None

    def restore(self, catalogue_id: str, collected: bool):
        self.notify_load_boundary()
        return self.observe_event(catalogue_id, collected)

    def load_save(self):
        self.notify_load_boundary()
        self.map_open = False
        self.map_icons.clear()

    def _sync_icons(self):
        if not self.map_open:
            self.map_icons.clear()
            return
        self.map_icons = {
            key for key, row in self.rows.items()
            if row["realm"] == self.realm and self.state[key] != "collected"
        }

    def collide(self, object_token: str):
        row = self.by_object.get(object_token)
        if row is None:
            # Incidental/non-custom collision callbacks do not replace an exact Raven
            # candidate. Ownership is resolved later by the exact prompt UID.
            return None
        if row["catalogue_id"] not in self.map_icons:
            self.selection = None
            return None
        self.selection = row["catalogue_id"]
        return self.selection

    def incidental_collision(self) -> None:
        """Model collision noise that must not expire an exact Raven candidate."""
        return None

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
        if self.state[catalogue_id] == "collected":
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
