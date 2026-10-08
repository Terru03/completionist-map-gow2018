# Windows 10 LTSC early startup crash

Date: 2026-10-06. Candidate: `CompletionistMap-v1.0.4-startup-test.zip`.

The supplied report points to a failure before normal graphics and mod startup.
The native source had an early AppCompat export that could allocate through its
uninitialized static CRT. This access violation was reproduced and fixed in both
DXGI layers. The affected PC still needs to retest: its report has no stack or
minidump establishing the exact export on that machine.

## Report evidence

Input: `../startup-support/GoW-startup-20261005-161723-3ec6909b.txt`
(relative to the checkout).

- Windows 10 Enterprise LTSC 21H2, build 19044.7725; Radeon RX 570.
- Supported `GoW.exe` SHA256:
  `caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452`.
- Root DXGI SHA256:
  `c925837d249d6d27cedd330e7ff554581372bb0a8095a5e4fd370e1844f09fe7`.
- Companion SHA256:
  `456f4ac30f55e121c612b56f4f7c0060ed8f1473588c09cf8db8673048327094`.
  Both DLLs match the shipped v1.0.1/v1.0.2 pair and the native manifest.
- Loader `version.dll` matches the local 0.22 loader by hash and size.
- Process 3000 has no window and almost no CPU time. Its module list contains
  `AcLayers.dll`, `AcGenral.dll`, and the local DXGI proxy. Neither the companion
  nor System32 DXGI is listed in this snapshot.
- Both mod logs are missing. Windows reports `0xc0000005` at
  `ntdll.dll+0x649f6`, rather than the earlier game graphics-object fault.

Loaded compatibility shims are evidence of the AppCompat path; they do not
establish which compatibility setting the player selected. The original report
did not collect those settings. Missing logs and a module snapshot alone cannot
identify the crashing instruction's callers.

## Reproduction and fix

Previously `SetAppCompatStringPointer` used the general export resolver. That
entered `InitOnceExecuteOnce`, built a heap-allocated System32 path, loaded DXGI,
and, in the outer proxy, initialized the native capacity patches. An AppCompat
call before `_DllMainCRTStartup` could therefore use an uninitialized CRT heap.

A test-only MSVC `_pRawDllMain` callback calls the same generated ordinal-8 thunk
before that DLL's CRT initialization. The original capacity implementation
crashed in `ntdll.dll` with `0xc0000005` on the Windows 11 test host. Its fault
offset was `0xc43d8`; offsets cannot be compared across different ntdll builds.
The shipped v1.0.1 DLL also fails the new deferred-replay test with
`AppCompat call initialized DXGI before graphics`.

Both proxies now return an AppCompat handler before entering the general
initializer. Its state has constant initialization. It retains the caller's size
and pointer without using the CRT, logging, loading DLLs, hashing files, or
starting workers. Normal DXGI initialization binds the real System32 setter and
replays the latest arguments. Later setter calls update Windows immediately.
An SRW lock serializes updates and replay; DLL loading occurs outside this lock.

This follows [Microsoft's DLL initialization guidance](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-best-practices),
which warns that loading libraries and using an uninitialized CRT during DLL
initialization can cause crashes. `DllMain` remains minimal. Supported EXE,
companion hash, instruction checks, and all three engine capacity patches remain
in place.

## Verification

- 13 bridge CTest cases and 5 capacity CTest cases pass. These include calls
  before CRT initialization, exact deferred argument replay and later updates,
  real COM graphics factories, Windows 10 export simulation, native capacity,
  and completion-state decoding/delivery.
- All 8 package and Windows PowerShell installer tests pass.
- Updated `DebugGoW.bat` passes PowerShell 5.1 parsing, installation discovery,
  redaction, real CMD execution with unusual paths, compatibility/redirection
  field collection, and save-guard checks. It now reads the exact game's HKCU,
  HKLM, and 32-bit compatibility flags and `GoW.exe.local` presence.
- ZIP CRC and all 20 runtime payload sizes/hashes verified. Compared with the
  existing v1.0.2 package, only the two DLLs and native manifest change. Existing
  v1.0.1 and v1.0.2 ZIP hashes remain unchanged. Companion pin and both manifest
  hashes match the rebuilt pair. No game EXE or loader DLL is included.

Local interactive game verification remains open. Windows commands in this
environment run in session 0. A candidate direct launch exited with a separate
`KERNELBASE.dll` / `0xe0000d11` event and no fresh mod startup log. A control
Steam launch with the original DLLs also produced no game window or fresh native
startup evidence. These attempts cannot establish an interactive startup result.
The original three native files were restored byte-for-byte and all save hashes
were unchanged. No save was loaded or played.

Evidence is retained in `build/startup-support-20261006/`, including native test
output, package verification, the original early-callback DLL, the launch
results, and native-file/save backups. That directory contains local development
data and is excluded from the distributable.

## Candidate hashes

| File | SHA256 |
| --- | --- |
| `CompletionistMap-v1.0.4-startup-test.zip` | `a00b667c8b73a47627f6a14239767d5593c36be791a3b88aa46b293b1e672b7b` |
| Root `dxgi.dll` | `923afa1bc59751722f32351ffc17d337ef86beec4a89066dee6909d4e226357e` |
| `collectible-base-dxgi.dll` | `9043eac673ae15cd4f4b5c2f5bc96c64d17aa1fd613d588ce2547532fcb8f02c` |

## Retest

Close GoW, extract the complete candidate ZIP, and run `Install.bat`. Preserve
the existing `completionist_backup`. Launch through the usual desktop launcher
and check the main menu, then map and compass after loading a save. Run the
updated standalone `DebugGoW.bat` after the attempt, including on success. A
native `*_DXGI_APPCOMPAT_REPLAYED` line records a deferred compatibility call;
the three `COLLECTIBLE_*CAPACITY_READY` lines confirm native setup.

Keep the native proxy installed with the expanded map data. Removing just that
DLL removes the required marker/entity/physics capacity patches. Use the complete
package's `Uninstall.bat` to restore the stock installation if necessary.

At the time of the candidate build no release had been uploaded. The reporting
player subsequently confirmed successful startup on 2026-10-06. These native
DLL bytes were retained in the Discord chest-tracking test and its production
v1.0.4 promotion. See the [release record](../releases/v1.0.4-release.md) for the
current package and Nexus review status.
