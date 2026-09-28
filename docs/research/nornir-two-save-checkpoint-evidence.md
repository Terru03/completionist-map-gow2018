# Nornir two-save checkpoint observation, 2026-09-25

Two different saves were captured as six full-memory process snapshots, with a
copy of the active `game.sav` at each stage. The capture session is outside the
repository at `../nornir-captures/20260925-064923`. The read-only capture used
separate God of War processes for Veithurgard (PID 50420) and the Mountain
(PID 49876). The pinned executable SHA-256 is recorded in the accompanying
JSON. Raw dumps and saves remain outside Git.

`tools/v0.10.5/analyze-nornir-checkpoint-carriers.py` decodes the exact staged
WAD checkpoint carrier in each dump using the existing validated checkpoint
graph parser. It reports the GameObject hash pair and typed fields for each
`__subobjs` entry, then searches all 20 copied save slots for an exact carrier
byte match. Its detailed output is `checkpoint-carriers.json` in the capture
session; the small evidence summary is
`docs/research/nornir-two-save-checkpoint-evidence.json`.

`tools/v0.10.5/prove-nornir-two-save-gameobject-identities.py` independently
rebuilds the two loaded chest hashes from their GameObject identity chains.
Both chains include the catalogue's exact placement identity and the stock
chest-script identity. The matching runic parent chains include the same
placement and the catalogue parent prototype. The Veithurgard chest is registry
238, slot 1477; its runic parent is slot 1402. The Mountain chest is registry
221, slot 1076; its runic parent is slot 1001. The detailed proof is
`gameobject-identity-proof.json` in the capture session.

| Save | WAD | Opened chest object hash | Runic parent object hash | Persisted after capture? |
| --- | --- | --- | --- | --- |
| A, Veithurgard | `Xpl200_Funeral` | `C0FF99FB89416EC1` | `F99036D21E9E96A4` | No copied save change at A3 |
| B, Mountain | `Peak720_SummitAscentHUB` | `895FDE6574116698` | `A76B9908BD4D60AC` | Exact carrier bytes in changed save slot 3 at offset 37344 |

After the player opened either chest, the WAD carrier added a GameObject entry
with `state = 4.0`, and a separate runic parent entry with
`challengeComplete = true`, `keysUsed = 3.0`, and `state = 1.0`. The Mountain
opened carrier in the copied save is byte-for-byte equal to the staged process
carrier (SHA-256 `b0090d75b487bb8ab1bf2f0720d92a201022bddce77e9202f69221d870a8df03`).
This directly establishes a persisted opened example for one chest and an
observed opened process example for a second chest. The field names and values
also distinguish the reward chest state from puzzle completion.

The Veithurgard staged carrier and copied save stayed byte-identical through
the first and second rune snapshots. After the chest opened, the staged carrier
changed but the copied save did not. The rune transitions therefore need a
separate live-state decode; absence of a checkpoint change does not mean the
seals were unchanged. It also means the Veithurgard after-open snapshot alone
does not prove persistence after a reload.

`tools/v0.10.5/analyze-nornir-live-seal-transitions.py` identifies each loaded
seal root from its exact catalogue GUID, follows its direct `gorunicN_break`
child, and reads a component at GameObject `+0x220` (vtable RVA `0xE0DEF8`).
The byte at component `+0x124` follows the player sequence in Veithurgard:
seal 01 is `0,1,1,1`; seal 02 is `1,1,1,1` and was already resolved at A0;
seal 03 is `0,0,1,1`. All three Mountain seals are `1,1` across B0/B1, where
the chest was ready to open before capture. This is a strong observed loaded
completion candidate across six distinct seals. The exact binding to the
stock `destructible.IsDestroyed()` API and an unloaded child query remain
unproved. The detailed `live-seal-transitions.json` is in the capture session.

These two observed GameObject hash pairs can seed a scoped save-state reader.
`tools/v0.10.5/read-observed-nornir-save-state.py` now reads the newest copied
save slot and reports `OBSERVED_OPENED` only for a unique exact chest hash pair
with `state = 4.0`. On this capture it reports the Mountain chest opened in B1
and unknown in B0; Veithurgard remains unknown in A0/A3 copied saves. It never
treats a missing checkpoint entry as an unopened chest.
The rest of the Nornir catalogue still lacks proved per-instance checkpoint
hashes and cold lookup. The static gate remains `BLOCKED_FAIL_CLOSED`; this
observation does not authorize runtime marker generation or Raven resource
reuse.
