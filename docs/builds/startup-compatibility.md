# v1.0.1 Startup Crash Report

Date: 2026-10-03. Release update: 2026-10-04. Branch: `codex/startup-compatibility`. Base: `bf0ab45`.

## Reports Read

- [Reddit r/GodofWar post](https://www.reddit.com/r/GodofWar/comments/1wwid6l/made_a_god_of_war_2018_pc_mod_for_collectible/): Past_Mammoth8420 reports no game window; removing mod fixes launch.
- [Reddit r/steamachievements post](https://www.reddit.com/r/steamachievements/comments/1ww5mtp/made_a_god_of_war_2018_pc_mod_for_collectible/): no crash report seen.
- [Reddit r/Completionist crosspost](https://www.reddit.com/r/Completionist/comments/1ww5ork/made_a_god_of_war_2018_pc_mod_for_collectible/): no comments shown.
- [Nexus Bugs](https://www.nexusmods.com/godofwar/mods/396?tab=bugs): issue 1143859, nobody2709. GoW.exe `1.0.475.7534`, timestamp `0x628e8031`, exception `0xc0000005`, offset `0x999ED4`. Loader log empty with dxgi.dll active. Removing DLL reaches `dictionary is full, cannot add another item`.
- [Nexus Posts](https://www.nexusmods.com/godofwar/mods/396?tab=posts): nibiru2013 reports same startup failure on Steam 1.0.13 with loader 0.22. Klibaski also reports failure. Removing mod restores launch.
- Bug author's [working loader log](https://bin.mudfish.net/t/442-4365-2122) and [failed loader log](https://bin.mudfish.net/t/046-7090-1712) read. Failed log stops at engine dictionary limit; no proof of a Lua-context dictionary defect.

Published v1.0.0 ZIP matched local original ZIP byte-for-byte:

```text
aa8985e031944d8971a4075a650b8c5de1f9a66a012fe2a0cb89b5d2aa4e985c
```

## Release And Replies

- v1.0.1 uploaded to [Nexus Files](https://www.nexusmods.com/godofwar/mods/396?tab=files), file ID `878`, as primary main file. Mod version, changelog, and install/support notes updated. v1.0.0 kept in archive.
- Nexus quarantined new ZIP. Download blocked pending safety review; no claim download live. No bypass or mirror used.
- [Reddit reply](https://www.reddit.com/r/GodofWar/comments/1wwid6l/comment/pdp3zml/) sent to Past_Mammoth8420: "Uploaded v1.0.1 on Nexus. Nexus review pending; please test once download live."
- Nexus shared startup thread reply `176731080` and SaneKRIEG crash thread reply `176731128` sent: "Uploaded v1.0.1. Nexus review pending; please test once download live."
- Same short reply sent on bug `1143859`, reply ID `5628021`. Bug left open as `New issue` for player retest.
- Each reply verified in rendered page. Release and reply screenshots in `build/startup-evidence`.
- User approved public source push and Nexus support review email on 2026-10-04. Source push and email in progress; not yet confirmed sent.
- [Native build guide](v1.0.1-native-build.md) gives pinned release dependency, DLL build order, companion hash pin, package steps, and uploaded file hashes.

## Proven Bugs

1. Bridge required all 20 system DXGI exports at fixed ordinals. One was `DXGIDisableVBlankVirtualization`, which [Microsoft documents as Windows 11 version 22502 minimum](https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_6/nf-dxgi1_6-dxgidisablevblankvirtualization). Windows 10 lacks it; later ordinals also shift. Old proxy fails graphics factories when lookup differs.
2. Outer capacity proxy checked EXE and native pair before resolving graphics. Unsupported EXE or rejected native setup left graphics factory unavailable too.
3. Installer did not check EXE or payload hashes. It could copy full expanded map data to an unsupported game build, or install corrupt files.

[Microsoft advises lookup by name for exports that vary across Windows versions](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-getprocaddress). Ordinals remain valid only for our own hash-pinned companion DLL.

Stock local EXE matches report version/timestamp. At reported RVA, instruction is:

```asm
0x999ECD  mov rcx, qword ptr [rip + 0x46b253c]
0x999ED4  mov rax, qword ptr [rcx]
0x999ED7  call qword ptr [rax + 0x40]
```

Failed DXGI factory leaves null graphics object and fits this fault. This link to each reporter remains inference: reports lack Windows version, startup native log, and full memory dump.

Removing dxgi.dll is not a fix. It also removes marker registry, entity-array, and UI-physics capacity patches. Expanded map then exceeds stock engine limits. This is not evidence that too many Lua hooks caused initial crash.

## Fix

- Both layers resolve System32 DXGI functions by name. Only three graphics factories required.
- Missing optional export returns `ERROR_PROC_NOT_FOUND` for that call only. Later factory calls still work.
- System32 graphics fallback ready before native checks. Rejected native setup logs cause, leaves snapshot unavailable, and does not poison graphics.
- Exact EXE hash, companion hash, and native instruction checks kept. No EXE disk patch; bridge does not write saves or progress.
- Installer checks EXE, each payload hash, path, and boot JSON before backup/copy. Art JSON written without UTF-8 BOM. Repeat install preserves original backup and adds no duplicate art entry.
- Builder checks native pair and rejects all inputs inside output before cleanup.
- v1.0.1 uses shipped v1.0.0 Lua/map/art data unchanged. Only two native DLLs and native manifest differ among 20 payload files. Scripts/docs also updated.

## Test Evidence

- Old shipped bridge fails real factory test under simulated Windows 10 lookup.
- Old shipped capacity proxy fails same test on unsupported host EXE.
- Fixed bridge: 11 CTest cases passed. Includes three real COM factories, normal/Windows 10 lookup, export contract, missing factory rejection, and native authority/delivery cases.
- Fixed capacity: 3 CTest cases passed, including both forwarding cases and instruction/capacity tests.
- Six PowerShell 5.1 install cases passed: unsupported EXE, corrupt/missing payload, invalid boot JSON, valid install with stock backup/art registration, repeat install.
- Two builder cases passed: mismatched native pair and source/either DLL inside output. All input files preserved on rejection.
- ZIP CRC, all 20 payload sizes/hashes, and unchanged non-native data verified.
- Full v1.0.1 installer run in clean fixture with real supported GoW.exe and loader DLL passed. All 20 installed hashes matched; art registered once; stock boot backup kept; EXE unchanged. Fixture was not used to launch game.
- Independent review found builder input-deletion edge; fixed with tests. Review then found no open code issue.
- Actual Steam game launches and save loads twice on this PC, with full quit between runs. First run registered only shipped family art pack; prior dev art pack not loaded. Second run used restored prior boot options. Log confirms all three capacity patches ready and native save-state reads accepted.
- Save SHA256 after both runs matched backup exactly. No manual save or progress change made.
- Full test run while game open hit expected environment conflicts: game owns bridge port; installer refuses open game. After full quit, fresh 11 bridge + 3 capacity + 8 package/install cases passed.
- On 2026-10-04, both DLLs rebuilt from clean staged-source archive with fresh official zlib v1.3.1 checkout. All 22 checks passed; rebuilt package CRC, all 20 payload hashes, companion pin, and no EXE/loader inclusion verified.
- Deep clean-copy path first caused four archived-fixture read failures. Fixture files present; resolving `CAPTURE_ROOT` removed long `native/raven-authority-bridge/../..` path. All 11 bridge checks then passed. Public build guide includes resolved fixture root and short-path note. No shipped native code change needed.

Map/compass UI check remains pending: Computer Use key input did not reach in-game controls. User asked to open map on this PC; no answer received during test. Startup fix verified, but no claim of full UI acceptance.

Candidate ZIP SHA256:

```text
35119c92f19ad2d2f219894d0cbf4591372a343b0e280503f22854edd1560f68
```

## Support And Gaps

Supported EXE: Steam 1.0.13 / file version 1.0.475.7534:

```text
caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452
```

Local machine: Windows 11 Pro build 26300, NVIDIA RTX 4070 Ti SUPER. Windows 10 export layout simulated in actual compiled DLL tests; no real Windows 10 game run yet. No Epic/modified EXE support claim. Graphics fallback alone cannot make expanded map data safe on unsupported EXE.

Laptop not needed to reproduce these defects. Real Windows 10 or affected-user retest still useful for full OS/GPU coverage. No claim that every reported PC now proven fixed.

Local backup: `build/startup-evidence/pre-game` contains prior DLLs, mods, boot JSON, settings, and save files. v1.0.0 ZIP left intact. Live game now has v1.0.1 native pair; prior boot options restored. Test game closed. Logs and repeat save-load screenshot in `build/startup-evidence`.
