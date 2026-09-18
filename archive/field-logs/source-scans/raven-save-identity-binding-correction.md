# Raven save-identity binding correction

The frozen Raven carrier contains three GameObject records after the kill, but only one is new.

- ALIVE already contains object hashes `0x165CD520758061E5` and `0xADB72E5C5003A8A0`.
- DEAD preserves both and inserts `0x98BE1707BA2D65A9` at record index 1.
- The inserted record is the value associated with the newly appended `ravenKilled` field.
- Therefore the first two hashes are surrounding persistent objects, not two additional Raven instances.

The exact read-only identity-vector capture for `0x98BE1707BA2D65A9` reconstructs:

```
6a40442bc7277743a15f2986a3279901
82bdafe150a9ea49ac27331f1525d1d5
160d2d64d4a5f04a93776e075d9a543c
805b030bf339564cb157837c52906465
```

This vector hashes exactly to `0x98BE1707BA2D65A9`.

It binds statically to `raven_642d0d164af0a5d4076e77933c549a5d`:

- the first three elements are the catalogue transform chain in root-to-leaf order, with byte index 12 decremented by one;
- the final element is the GameObject identity stored at payload `+0x6C` in the record referenced by the Raven leaf transform's `prototype_id`.

This supersedes the earlier unproven hardcoded one-to-one labels that associated all three frozen hashes with three VikingFuneral Ravens. The hash/token codec itself remains valid; only those catalogue labels were incorrect.

The production mapping must be generated using the native WAD identity recipe, not by assigning the two pre-existing carrier records to Raven instances.
