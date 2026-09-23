# Cipher Chest static gate — 2026-09-23

Branch: `codex/collectible-cipher-chests`. This pass read shipped quest/resource DCBs and WADs offline. God of War stayed closed. No game or save files changed.

Native quests `Quest_SonLanguage_Muspelheim` and `Quest_SonLanguage_Niflheim` each have target **4** in `quests.dcb`. `resources.dcb` contains `MuspelheimCipherPiece` and `NiflheimCipherPiece`. These are item/progression targets, not a physical chest count. The user-supplied external guide baseline is **13 purple language chests**; keep it distinct from the 8 quest pieces.

`cipher-chest-static-gate.json` pins source hashes and exact quest record offsets. It scans every shipped WAD for either cipher item name. Of 123 matching WADs, 119 hold the shared `interact_chest_standard` script with both item names. Other matching compiled scripts are logged by name and offset. No non-script WAD record in the scan contains either item name. Thus the shared chest script cannot identify which placed chest awards a cipher piece. It also cannot identify whether any specific purple chest is repeatable, a template, or counted.

Physical chest census, stable per-chest cipher reward identity, persistent unloaded `OPENED` state, and native marker coverage remain unproved. The gate is `BLOCKED_FAIL_CLOSED`, with no physical Cipher Chest rows and no marker generation. The master inventory must not create chest rows from the 8 quest targets or 13 guide count.

Rebuild and test:

```text
python tools/v0.10.5/audit_cipher_chests_native.py --output docs/research/cipher-chest-static-gate.json
python -m unittest discover -s tools/v0.10.5 -p test_cipher_chest_static_gate.py
```

Next proof: resolve the per-placement loot table or reward record that grants each cipher piece, then inspect exact world transforms, per-object completion, and stock marker coverage.
