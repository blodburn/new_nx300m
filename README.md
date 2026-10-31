# NEW NX300M — Film Simulator research

Experimental image-processing source for investigating **Samsung NX300M** film-look processing. **This is not installable camera firmware** and must not be flashed onto a camera.

## Features

- **13 fixed look selections:** Samsung Original passthrough, 7 experimental Fujifilm-style and 5 Leica-style looks. Brand names describe visual research targets; no manufacturer endorsement or affiliation.
- High-bit-depth unpacked Bayer16 demosaicing, white-balance/exposure/highlight mapping before RGB8 conversion.
- Row-stream processing instead of a full-frame RGB16/RGB8 intermediate, with transactional `begin → write_row → commit / abort` sink.
- Host-only standalone baseline **JPEG 4:4:4 and 4:2:0** encoder for synthetic test images, **not** the NX300M's original JPEG codec.
- Host-only Y/C 4:2:0 staging model with explicit **experimental** CbCr / CrCb order. This does **not** establish the physical camera memory layout.
- Regression tests for RAW byte preservation, Samsung Original no-op, pixel equality, JPEG container validity and failure rollback.

## Host build

Requires: C11 GCC-compatible compiler, `make`, Python 3. No vendor SDK, firmware blobs or original camera libraries required.

```sh
make test
make bench
```

`make test` compiles and executes 14 independent sanitizer-tested C suites plus one GUI callback runtime C suite, five JPEG SOF parser tests, five Y/C probe CLI tests, six ARM ELF ABI audit tests, and an EFL syntax-only check. `make bench` exercises full-resolution **synthetic** images, which are not representative of camera hardware performance.

JPEG test encoder verification includes **odd 33×25 dimensions**, end-to-end decode of the 4:2:0 sample, independent SOF sampling readback, unchanged RAW bytes, original-preset bypass, EXIF APP1 byte-copy, and refusal to overwrite existing images. Both JPEG modes use row scratch, not a full RGB8 image buffer. For an offline 20 MP JPEG 4:2:0 benchmark, compile the host JPEG benchmark or run `.build/bench_jpeg 420` after `make bench`.

**Important:** Producing a standard 4:2:0 JPEG bitstream does *not* establish compatibility with Samsung's proprietary 4:2:0 capture-memory format, DMA ownership, original JPEG encoder, or EXIF/MakerNotes. There is no on-camera integration yet.

## Picture Wizard symbols found in an offline capture library

An offline, read-only ELF metadata scan of a *partial research extraction* found four Picture Wizard-related dynamic symbol names in `libcapture-fw-slpcam-nx300.so`, including `CProcessParameter::GetPictureWizardMode()` and `GetPictureWizardParameter(...)`. It also found `convertUserData_DIALMODE(...)`, which is **not evidence of a hardware dial EFL callback**. Nine capture libraries were inspected, with 13 dependency references resolving within the small research sample and 84 missing from the sample. These counts do not imply missing libraries in full firmware. **Firmware 1.14 identity, physical device behavior, and safe UI/ISP calls are unverified.** See [the evidence and next verification gates](docs/NX300M_PICTURE_WIZARD_SYMBOL_EVIDENCE.md).

`research/nx300m_capture_elf_surface_audit.py` scans only ELF dynamic metadata with `readelf` and `c++filt`. Seven fixture unit tests were added to `make test` (**15 C regression executables and 23 Python tests**); no proprietary ELF or firmware is distributed.

## 1.14 Picture Wizard function-body comparison gate

An unofficial [Samsung NX300M firmware archive](https://nxfiles.nx.tc/files/NX300M/Firmware/) lists `NX300M_FW_v1.14.zip`, but the current development environment **could not download it without network approval**. No authenticated 1.14 firmware image or extracted 1.14 ELF has been inspected. The older research ARM ELF yielded four Picture Wizard function body lengths (96, 172, 1036, 924 bytes) and independent cryptographic fingerprints. New `research/nx300m_picture_wizard_abi_gate.py` compares read-only ELF-mapped function bodies and refuses to infer compatibility solely from matching symbols. Seven synthetic fixture tests detect modified/missing functions. **Neither identical function bytes nor these historical offsets authorize firmware 1.14 patching.** See [1.14 ABI comparison evidence](docs/NX300M_PW_114_ABI_COMPARISON.md).

## Fail-closed Picture Wizard 12-versus-13 routing guard

The older Ghidra research shows **12 original Samsung Picture Wizard dispatches**; Film Simulator uses **13 fixed looks** and its own unrelated IDs. The new host-only `research/nx300m_picture_wizard_route_guard.[ch]` never sends experimental IDs to native Samsung functions or changes raw buffers, camera Y/C, or the original native Picture Wizard mode. Samsung Original passes through unchanged. Experimental looks can be planned **only** for an explicitly validated independent **host-owned RGB888** frame in JPEG or RAW+JPEG simulations; all direct experimental camera routes and RAW-only modifications are rejected. `research/test_nx300m_picture_wizard_route_guard.c` verifies **156 state combinations**, malformed IDs, legacy Leica ID aliases, and the unchanged RAW buffer. See [safe native/Film Simulator separation](docs/NX300M_NATIVE_MODE_ROUTE_SAFETY.md). This is a routing policy, **not** a real 1.14 native firmware integration.

## Host-only non-destructive RGB copy integration

`research/nx300m_host_capture_copy_adapter.[ch]` connects saved Film Simulator settings with the **fail-closed Picture Wizard route guard** and the host RGB filter. Unlike the older in-place research API, it validates explicit source/destination byte lengths, stride and partial overlaps, caps scratch allocation at **128 MiB**, and processes the image in a private copy. A caller-owned destination is changed **only after successful full-frame processing**. Original mode, missing/corrupt configuration, RAW-only processing, unverified RGB input and any experimental camera-source request never modify it. Source and RAW bytes remain unchanged. This is an offline RGB output, **not** a real camera JPEG/ISP hook. The new C sanitizer suite checks all 13 looks, size/overlap errors, unchanged padding and output failure paths. See [host RGB copy integration](docs/NX300M_HOST_COPY_INTEGRATION.md).

## Verified SLP internal version and offline ZIP/BIN integrity

The existing private reference is named `nx300m_mfw_1.1.bin`, but its **internal Samsung SLP firmware version is 1.15**, not 1.1. MFW 1.1 is the modified-release label, not the underlying Samsung native version. All **five image JAMCRC checks plus the pcache JAMCRC** passed on its 333,237,352-byte binary. This does not prove the modified image is original Samsung firmware, and it is NOT a 1.14 comparison.

New read-only `research/nx300m_slp_firmware_integrity.py` reads an existing local BIN or ZIP (without extraction), rejects wrong camera models/versions and damaged/traversal archives, streams all six JAMCRC checks and SHA-256, and never modifies camera firmware. Nine synthetic tests verify corruption, bad metadata and ZIP handling; the full test suite has **17 C programs and 39 Python tests**. See [firmware SLP integrity evidence and version correction](docs/NX300M_SLP_PACKAGE_INTEGRITY.md). The original **1.14** binary remains unavailable for actual ABI comparison.

## Picture Wizard setter assembly evidence: 13 local pointers are not 13 active styles

Read-only analysis of the saved modified-firmware 1.15 reference `set_picture_wizard(int)` Ghidra evidence found **95 ARM instructions**, a clamp to 0..12, and **13 pointer entries initialized on the local stack**. The captured function has no visible direct call and no visible writes outside local stack. **This is not proof that the camera supports 13 native style choices or that this function actually applies Picture Wizard settings.** A separate older analysis described 12 native dispatch entries; the two counts refer to different evidence. None of it proves firmware 1.14 behavior. New `research/nx300m_picture_wizard_setter_evidence.py` and seven independent synthetic fixture tests check this narrow pattern without executing vendor code. See [Picture Wizard setter machine-code evidence](docs/NX300M_PW_SETTER_ASSEMBLY_EVIDENCE.md).

## Picture Wizard UI event → generic setter direct-call evidence

Read-only analysis of the older, **modified Samsung 1.15** `di-camera-app-nx300` ELF found direct ARM `BL` instructions from `CAPPGUIGadgetPWState::handle(ISAFEvent const*)` to `GUI_Set_System_Value(int,int,int,int)` (**11 callsites**) and from the Picture Wizard Minus/Plus slider handlers (**3 callsites each**). Other detected relationships connect the Picture Wizard UI to focus and layout handlers. This is **not** proof of the parameter ID, Samsung capture IPC write, actual ISP behavior or stock **1.14** compatibility. The unrelated `set_picture_wizard(int)` routine has no observed direct ARM BL callers in this bounded scan. New [static UI callsite audit](research/nx300m_pw_ui_bl_call_audit.py) and eight synthetic ARM fixture tests make this result reproducible without publishing vendor code. See [UI/IPC callsite evidence](docs/NX300M_PW_UI_IPC_CALLSITE_EVIDENCE.md). Full host testing includes **17 C regression executables and 54 Python cases**.

## Picture Wizard UI argument and menu-dispatch evidence

Read-only static analysis of **18** `GUI_Set_System_Value(r0,r1,r2,r3)` callsites from the older modified **Samsung SLP 1.15** Picture Wizard UI shows syntactic immediate pairs `(r0,r1)=(4,4)` at 12 sites, `(11,4)` at 3 sites, and `(2,4)`, `(5,4)` and `(7,4)` at one site each. These are **not validated Picture Wizard setting IDs**. The generic setter directly calls `UI_Set_Menu_Info_By_GUI`, which has two direct BL callsites to `UI_Set_Capture_Menu_Info_By_GUI`; control-flow conditions, native IPC and real ISP changes are still unverified. The offline [argument analyzer](research/nx300m_pw_setvalue_arg_audit.py) does not invent values for dynamic or conditionally assigned registers. Eight synthetic fixture tests and [scope/evidence documentation](docs/NX300M_PW_REGISTER_ARGUMENT_EVIDENCE.md) are included. `make test` covers **17 C executable suites and 62 Python tests**. None of this proves equivalence to stock NX300M **1.14**.

## Picture Wizard Capture-menu dispatcher: two conditional branches

The older **modified Samsung NX300M 1.15** `UI_Set_Menu_Info_By_GUI` function has **two guarded** direct ARM `BL` callsites to `UI_Set_Capture_Menu_Info_By_GUI`. Read-only machine-code analysis verifies (A) a call to `UI_Get_State(2)`, comparison with `7` and a branch that **skips** the capture handler when the comparison is false; and (B) two comparisons of a menu record value against `899` and `950` and a byte flag zero test before another capture callsite. These constants are **not verified Picture Wizard IDs**, and neither path is proven reachable at runtime from an actual PW UI event. New [conditional capture branch audit](research/nx300m_pw_capture_branch_audit.py), eight synthetic unit tests and [evidence documentation](docs/NX300M_PW_CAPTURE_CONDITIONAL_DISPATCH.md) distinguish static reference callsites from real IPC/ISP execution. Full `make test` covers **17 sanitizer C suites and 70 Python tests**; no original **1.14** firmware equivalence is claimed.

## Capture menu value → DB setter: verified static ARM call graph

Read-only inspection of the older modified **Samsung NX300M 1.15** camera UI ELF confirmed six groups of direct ARM `BL` call instructions (**25 machine callsites**): `UI_Set_Capture_Menu_Info_By_GUI` → `UI_Set_Capture_Menu_Value` (2) and `UI_Set_Value` (2); `UI_Set_Capture_Menu_Value` → `UI_Set_Value` (18); `UI_Set_Value` → `UI_Set_Value_Capture_Menu` (1); and `UI_Set_Value_Capture_Menu` → `UI_Get_DB_ID_Capture_Menu` (1) and `UI_Set_DB_Value_Capture_Menu` (1). This static chain does **not** prove that a PW event reaches those calls, that a persistent DB is changed, or that IPC/ISP processing occurs. The initial graph audit excluded the DB setter body; **a subsequent jump-table audit proves real preference API callsites in executable code referenced by a 205-entry table**. New [read-only Capture DB graph audit](research/nx300m_pw_capture_db_chain_audit.py), eight synthetic fixture tests and [source evidence](docs/NX300M_PW_CAPTURE_DB_CHAIN_EVIDENCE.md) explicitly preserve this distinction. Host `make test` covers **17 C sanitizer programs and 78 Python tests**. No original stock **1.14** ELF equivalence or safe camera execution is established.

## Capture preference jump table: corrected direct external preference API evidence

Read-only analysis of the modified NX300M 1.15 reference shows `UI_Set_DB_Value_Capture_Menu` contains a **205-entry computed ARM jump table**. The table words are data pointing into executable blocks. Static ARM `BL` instructions and ELF **R_ARM_JUMP_SLOT** relocations identify **193 `pref_set_long` calls** (192 simple blocks and one exceptional conditional block), **two `pref_get_long` calls**, and one `slpcam_print_info` call. **Twelve** table indices lead to a default no-op return. Our earlier description treating the entire switch region as spurious BL-like data was incomplete: only the jump-table words are data, while target blocks contain genuine preference API call instructions. New [read-only preference jump-table audit](research/nx300m_capture_pref_jump_table_audit.py), [corrected source evidence](docs/NX300M_CAPTURE_PREF_JUMPTABLE_PREFERENCE_API.md) and eight synthetic tests verify this distinction. Host `make test` covers **17 C programs and 86 Python tests**. Picture Wizard-specific preference keys, runtime persistence, native Capture IPC, ISP behavior, and original NX300M **1.14** ABI remain unverified.

## Capture UI numeric value → DB-ID switch evidence

Reference-only analysis of the older modified **Samsung SLP 1.15** camera UI ELF identifies a **209-entry** absolute ARM switch in `UI_Get_DB_ID_Capture_Menu` mapping numeric selectors **3..211**. The case categories are **102 default-zero returns, 89 immediate-return blocks, 16 helper-call blocks, and 2 conditional helper-call blocks** (108 distinct target blocks). Numeric input `39` follows a local helper call, but previous observation of an unrelated `r2=39` in Picture Wizard UI handling is **not proven to flow to this numeric selector**. This is **not** proof of a Picture Wizard-specific preference key, runtime storage, Capture IPC/ISP or original stock **NX300M 1.14** equivalence. New [read-only UI→DB-ID switch analyzer](research/nx300m_capture_ui_db_id_audit.py), [detailed evidence](docs/NX300M_CAPTURE_UI_TO_DB_ID_REFERENCE.md) and eight synthetic fixture tests are included. Host `make test` passes **17 C executable suites and 94 Python cases**.

## UI numeric selector 39 → preference key candidates (reference-only)

Offline research on the modified **Samsung NX300M 1.15** reference connects Capture UI numeric item **39** to a helper that directly calls `UI_Get_Value(37)`: result values **1..12** map to DB selectors **53..64**, whose `pref_set_long` local `r1` keys are **236..280** in steps of 4; other result values map to DB selector **52**, key **868**. This is an exact static chain through the 209-entry UI-to-DB and 205-entry DB-to-preference switches in one modified reference binary. **It does not establish that a real Picture Wizard event uses UI numeric item 39**, or that any of these keys change capture IPC, the ISP, JPEG/RAW processing or original NX300M **1.14**. New [UI39 preference chain audit](research/nx300m_ui39_pref_key_chain_audit.py), eight synthetic tests, and [source evidence](docs/NX300M_UI39_PREF_KEY_CHAIN_REFERENCE.md) require matching instructions and refuse changed keys/branches. Host `make test` covers **17 C sanitizer executables and 102 Python tests**.

## Picture Wizard event → Capture item 39: conditional machine-code path

On the existing **modified Samsung SLP 1.15 reference only**, the Picture Wizard state handler calls `GUI_Set_System_Value(5,4,39,unknown)`. The generic wrapper copies all four arguments to a `tag_MENU_INFO`, whose first field=5 and third field=39 are preserved across the UI menu dispatcher. **Depending on dynamic `UI_Get_Value(1008)` and `UI_Get_State(2)` state**, the menu may call the Capture dispatcher. Its command-5 switch forwards item 39 to `UI_Set_Capture_Menu_Value(39,unknown)` when the guard permits it; item 39 does not match seven exceptional Capture items. This is a **verified conditional static route**, not proof that any user event actually reached Capture, persisted a preference, affected ISP/JPEG/RAW, or works on original **NX300M 1.14**. New [offline route witness](research/nx300m_pw_ui39_capture_route_audit.py), [ARM callpath evidence](docs/NX300M_PW_EVENT_TO_CAPTURE_ITEM39_CONDITIONAL_ROUTE.md), and eight synthetic negative/positive tests verify the boundaries. Host `make test`: **17 C executables, 110 Python tests**.

## Important limitations

The source-backed analysis used **MFW 1.1 (a modified release based on embedded Samsung NX300M 1.15)**; compatibility with an actual device running **firmware 1.14 is unverified**. There is no validated ARM firmware hook, no native camera SRAM/DMA adapter, no supported full-brick recovery, and no verified preservation of Samsung EXIF/MakerNotes on physical camera output. The Y/C byte layout, colorspace and stride need to be measured on an actual camera before any hardware bridge could be built.

The public source tree intentionally excludes firmware images, extracted proprietary shared libraries, original RAW photographs, private configuration, third-party binaries and generated image/binary artifacts.

## Layout

- `research/nx300m_bayer_prejpeg.[ch]` — experimental Bayer16-to-film pipeline
- `research/nx300m_linear_prejpeg.[ch]` — high-bit-depth exposure/WB/shoulder
- `research/nx300m_film_menu.[ch]` — saved fixed 13-look selector
- `research/nx300m_host_jpeg_sink.[ch]` — offline scanline-to-JPEG writer with atomic create-only publication
- `research/nx300m_host_native420_bridge.[ch]` — offline two-region Y/C type-1 geometry study
- `research/test_*.c` and `research/bench_*.c` — tests and synthetic benchmarks

## License status

This code is published for inspection. **No open-source license has been selected.** Public availability does not by itself grant permission to copy, modify or redistribute; a license can be chosen separately by the repository owner. Original brand names, proprietary firmware and vendor intellectual property remain their owners' property.

## NX300M 1.14 integration gate and read-only Y/C probe

See [native integration gates](docs/NX300M_114_INTEGRATION_GATES.md).

Build with `make probe` to inspect *previously copied* same-stage Y/C and RGB888 data:

```sh
./.build/ycc420_probe WIDTH HEIGHT Y_STRIDE C_STRIDE RGB_STRIDE copied_y.bin copied_c.bin matching_rgb888.bin
```

The probe only compares two full-range BT.601 interleaved chroma hypotheses. It does not know the camera's original Y/C layout and will return `INCONCLUSIVE` if the evidence is inadequate. A normal JPEG or SRW does not provide the same-stage Y/C memory dump. No camera firmware is modified or executed.

## NX300M Tizen Camera Platform

NX300M uses the Linux-based **Tizen Camera Platform** (DRIMeIV); userland ARM ELF software and Samsung's proprietary image-processing/ISP/JPEG pipeline are distinct. See [Tizen architecture and safe preflight](docs/NX300M_TIZEN_ARCHITECTURE.md).

The new read-only offline tools are `research/nx300m_tizen_elf_audit.py` for checking ARM EABI5 and whether two versions' individual ELF libraries are byte-identical, and `scripts/nx300m_tizen_readonly_probe.sh` for reporting generic OS/library presence **only from an already authorized device shell**. Neither tool modifies firmware or provides a way to bypass camera access.

Community NX300M modified firmware documents restoring `autoexec.sh` with **1.15** after update. Its safety or reversibility on a camera currently running **1.14** is not established. Do not flash or substitute ARM function offsets between firmware versions without verification.

## Tizen Film Simulator — standalone rotary UI

The new [Tizen EFL Film Simulator UI](docs/NX300M_TIZEN_FILM_MENU.md) provides a research-only right-side preset list and **rotate → preview → confirm/cancel** workflow across all 13 fixed looks. On-screen previous/next buttons and intensity controls are absent.

The host-tested controller saves only after confirmation to an explicit caller-provided path; cancel and failed persistence retain the previously selected look. The GUI source is syntax-checked against a **host stub**, not a verified NX300M 1.14 ARM/EFL sysroot. Hardware dial event names, Picture Wizard integration, image-processing hooks and flash safety remain unverified.

`make efl-check` performs host-only C syntax checking. `make tizen-efl` **refuses** to build without explicit compatible `TIZEN_CC`, `TIZEN_SYSROOT` and `TIZEN_PKG_CONFIG_LIBDIR`. No installable camera firmware or tested ARM executable is provided.

## Explicit physical-key evidence gate

Input actions are **disabled by default**. An explicit four-key mapping is required for clockwise, counterclockwise, confirm and cancel; otherwise all unrecognized EFL key events are ignored. Desktop-only mapping requires the separate `NX_FILM_DEMO_KEYS=1` opt-in. The bounded `NX_FILM_LOG_KEYS=1` diagnostic prints at most 32 printable event keynames in an already-authorized EFL session. These are observations, not evidence of any installed NX300M 1.14 dial mapping. See [Film UI documentation](docs/NX300M_TIZEN_FILM_MENU.md).

A guarded offline ARM cross-build script at `scripts/build_tizen_efl.sh` refuses to run without a verified original matching toolchain and sysroot; it also checks the emitted ELF class/machine/EABI before accepting any output. No device firmware is changed.

## EFL user-interface callback integration regression

New `make efl-runtime-test` builds and runs the **actual standalone EFL UI translation unit** with a host-only fake Elementary/Evas event loop. It validates **six complete GUI scenarios**, including disabled key mapping by default, opt-in keyboard demonstrations, explicit custom bindings, a refused incomplete keymap, missing settings path, atomic confirmation, cancel rollback, sidebar state and a bounded keyname log. `make test` includes it, with 15 total C regression executables and 16 Python tests. This is **not** the real NX300M firmware 1.14 UI runtime, physical camera dial, or an on-camera JPEG processing test.

Firmware source verification is tracked in [1.14 original image provenance](docs/NX300M_FIRMWARE_114_PROVENANCE.md). A historical third-party listing does **not** establish authenticity or a safe flashing/recovery path.
