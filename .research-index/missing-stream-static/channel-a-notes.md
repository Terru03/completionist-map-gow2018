# WAD record + Channel A static findings

EXE read only: G:/SteamLibrary/steamapps/common/GodOfWar/GoW.exe.
Known SHA-256 caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452.
Addresses below are module-relative RVA. Evidence: channel-a-native.txt.
No game launched. No process opened. No game/save write. No tracked edit.

## Record map

- +00..1F: 256-bit ResourceWads dependency set, not four pointers. 67B060..67B06B clears it; 67B099 obtains loaded WAD ResourceWads property; 67B0E7 ->67AB60 resolves each resource WAD name against module+22DC1B0 stride70. 67AC89..67ACB5 sets bit for resource index in this record. Reciprocal staged-record bit lives in resource record at 67AC29..67AC76. Consumer67B150..67B1F6 reads four qwords /256 bits and binds resource WAD objects into loaded owner+88 pointer slots (67B1CF). These metadata survive full-record save framing but rebuilt from loaded assets.
- +20: packed lifecycle/configuration flags. Bits2..9 hold low byte from6D3150(name), a WAD_ name-key lookup against global22E7980; constructor67A9A0..67A9B2. Signed extraction used as eviction level at82D7B5..82D7C6. Bit0 selects restore application at23FEB8 and path building at66BB10. Bit11 set and bit13 clear gate fresh serialization of loaded native slots at82D858..82D872. Bit18 marks loaded record binding at82D212, with +28 slot index. Bits28/29 cleared after Channel A serialization at82B3CD..82B3F6. Bit19 indicates +A4 stamp was assigned at82C957. Other bits remain unnamed; no invented state names.
- +24: logical WAD key. Constructor67A99D assigns recordIndex+0x12. Resident owner+C3C mirrors key at82D203. Name lookup673131..67313A returns key. 5494A0 finds record by key then5494C8 hashes record+84 name for external GameObject save identity. Not catalogue hash itself.
- +28: signed loaded native slot index; -1 means no bound slot. Load resets82CF77; bind82D219 and reciprocal slot+EE18 at82D21D. 25D05D..25D07A uses index to get array281C210[index*EE28].EE20 loaded WAD owner.
- +2C..2F: no semantic access proven; likely alignment bytes but kept unknown.
- +30/+38/+40: Channel A descriptor start pointer/cursor/u32 total byte size. +38 is mutable cursor, not an independent start/end or separate payload. 667380 reads at cursor then increments it;82C7F9..82C7FC resets cursor=start. Pool owns bytes. Main envelope is u16 packed byte count then count bytes. Producer82CC35 ->82B250, consumer6740E8..674120. Total descriptor includes prefix.
- +44..47: no semantic access proven; descriptor tail/padding unknown, serialized by raw record copy.
- +48/+50/+58: Channel B descriptor, same start/cursor/u32 byte size mechanics. Producer82CC81 ->82B070. B restore loader668747..668758 and82CE86..82CE97 sets both pointers to shared pool and size; outer WAD save emits name32+descriptor24+payload at82D702..82D729.
- +5C..5F: no semantic access proven; descriptor tail/padding unknown.
- +60: u32 snapshot of native slot+5E10 (Channel A extracted Lua byte count), stored82CCC2..82CCC8.
- +64: u32 snapshot of native slot+A614 (Channel B extracted Lua byte count), stored82CCCA..82CCD0.
- +68: u32 count of linked records in native slot+200 list; increment82CCF0..82CCF3.
- +6C/+70/+74/+78/+7C/+80: six u32 counts among that list, selected by node+70 bits1/2/4/8/10/20. Increments82CD08/82CD11/82CD1A/82CD23/82CD2C/82CD35. Do not treat these qword groupings as pointers or stream offsets. Counts cleared at82CCAE..82CCBF before each channel snapshot. Semantic object subtype names unknown. Whole record persists counters through82D899/82CF69; no separate semantic consumer proven in bounded trace.
- +84..A3: 32-byte NUL-terminated WAD name. +A0 is final four bytes of name storage, not separate dword field. Name32 separately saved for B at82D707, compared at673117 and82D187, copied67A960..67A96D. Full name capacity follows next proven field boundary, no assertion that all producers check length.
- +A4..A7: u32 packed stamp made from eight ASCII digit bytes at globals1227CC6,CC7,CC9,CCA,CCC,CCD,CCF,CD0, at82C8CB..82C954; flag19 set. Constructor zero67318E. Exact source string meaning/date/build semantics unknown; no pointer.

## Pool lifetime

Pool base22C6940 /used22C6938. New/replaced descriptor starts at pool+used via82B28B..82B2A6, then global22C6150 points at active descriptor.667470 writes bytes, advances descriptor cursor+8, size+10, and global used;667380 reads and advances cursor with bound test.667230 removes old descriptor bytes by memmove3ED3A6 at66725B; repairs both A/B start/cursor pointers of later pool slices at667274..66729C; shrinks used6672B4. Cursor reset after serialization82B3FC and extraction82C7FC. No decompressor in this path.

## Channel A exact forward path

1. 82C820(false) collects native WAD state;82CC0C ->82B820 fills native Lua count+5E10/data+5E14;82CC35 ->82B250(nativeSlot,record+30).
2. 82B250 writes native bit stream to stack64KiB scratch.82B31D ->23F580 includes WAD state.23FA1E writes Lua byte count in16 bits viaA20220;23FA4C writes each Lua byte in8 bits. Prior variable objects use17-bit counts, so Lua bytes need not align to byte boundary.82B329 ->2193C0 appends additional state.82B38F writes u16 byte length;82B39C writes packed bytes via667470. No compression.
3. On WAD load,673D00 at6740E1 reads current staged record pointer from module+4FE9BF0.6740E8 selects record+30;67410D reads2 prefix bytes to module+2D43F24,674120 copies that length to module+502B2B0. Same logic in82C7B0.
4. 82C4E0 initializes bit reader from502B2B0 (82C521), rounded capacity=(u16length+3)&~3 (82C518..82C53B), initial32-bit BE word via bswap82C54C.82C566..82C678 selects resident native slot by loaded owner+C3C matching input WAD key.82C5BC ->23FAA0(nativeSlot,reader);82C5CE ->2197A0(reader,wadKey) continues state.
5. 23FAA0 reads Lua count16 at23FE25 usingA20280, stores nativeSlot+5E10 at23FE39; reads each byte8 at23FE63, stores inline slot+5E14 at23FE77. A20280 is MSB-first reader (next BE32 word bswapA202F5, advanceA20314). Native bit reader capacity is rounded outer size; observer must use true outer bits and fail closed.
6. After other restore work, only if staged flags bit0 is set (23FEB8), loadedOwner=[slot+EE20], LuaClient=[loadedOwner+1C78] nonnull and client+0C bit0 set:240047 calls [client.vtable+80] withRCX=client,RDX=slot+5E14,R8D=slot+5E10. Parent already proves LuaClient +80 ->5B2280 ->7E9550.

Native slots: module281C210,64 entries,strideEE28. +EE18 staged-record index;+EE20 loaded WAD owner. Inline Channel A Lua capacity implied by next count field: A614-5E14=4800 bytes, but explicit native bound check of this particular size not proven. A global packed scratch502B2B0 reused per WAD; per-record A pool slices retain packed data for nonresident WADs, so offline transformation can operate without force loading.

Raw exact identity absence in Channel A is NOT exclusion proof. All8 MSB bit phases recover byte runs, but extraction still needs exact native field boundary or explicit candidate status. Reuse solved inner Lua carrier decoder; do not invent new userdata codec. Existing capture report lacks raw payload bytes. Exact next step: bounded RPM capture all A slices plus table metadata; recover bit-aligned carrier candidates and prove native envelope/field framing. Counter+60 offers cross-check of expected inner Lua byte length but is not proof of where its bytes begin, and can be stale relative to payload if fresh channel differs.
