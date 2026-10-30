# NX300M capture ELF linkage and Picture Wizard evidence

## Scope and provenance

This is a **read-only** investigation of a partial set of previously extracted Samsung NX300/NX300M research libraries under `nx300m/analysis/capture_libs`. The provenance of these objects is the earlier NX300M MFW 1.1 research set. **They have NOT been proven byte-identical to the owner's installed NX300M firmware 1.14.** No proprietary ELF library, firmware, image, or byte dump is included in this public repository.

## Actual inspection results

| Evidence category | Static result |
|---|---|
| Shared ARM ELF objects inspected | **9** `.so` files in the partial capture-libraries folder |
| `DT_NEEDED` references resolving within this small sample | **13** dependency edges |
| Other `DT_NEEDED` references absent from this extracted subset | **84** dependency edges |
| Real complete 1.14 Tizen userland and GUI executable | **Not available** |
| Physical Picture Wizard / EFL callback hook | **Not established** |
| Execution or installation on device | **None** |

Unresolved dependency edges represent missing files **within the small analysis folder**, not necessarily absent from Samsung's full firmware filesystem.

### Picture Wizard candidates, defined in the existing capture research ELF

The following symbol names were demangled from the ELF dynamic symbol table of `libcapture-fw-slpcam-nx300.so`. Only existence of a symbol is established, not a safe API contract:

- `CProcessParameter::GetPictureWizardMode()`
- `CProcessParameter::GetPictureWizardParameter(CProcessParameter::T_PWPARAM&)`
- `CProcessParameter::updatePictureWizardBracket()`
- `CCapCmdIf::setPictureWizardBracket(int, int, int)`

`convertUserData_DIALMODE(int, int*)` is also present. Its name refers to **dial-mode data conversion**, and must **not** be taken as evidence that an Evas key-down callback or the physical NX300M selection wheel is exposed through this function.

### Image pipeline candidates

- `libmm-type.so` defines `CYcc::GetY0()`, `GetY1()`, `GetC0()`, `GetC1()`, `GetType()`, and `VerifyBuffer()`.
- `libmm-photo.so` imports these CYcc methods, showing a link relationship to the type library. Import existence alone does not prove a readable or writable buffer address.
- `libcapture-fw-slpcam-nx300.so` defines `CaptureStillImage` and `CFrontEndInterface::stillCapture(CCapStillShot*)`.
- `libsif.so` includes `DscJPEG::StopFileSave()` and `DscImage::SaveExifImage(char*, unsigned int)`.

The script's bounded metadata inspection did **not establish a working Tizen EFL / Picture Wizard UI connection**. The input sample is incomplete, and absence of an imported EFL symbol in these libraries does not mean the original camera UI has no other interface.

## Reproducible commands

```sh
python3 research/nx300m_capture_elf_surface_audit.py \
  --root /path/to/preexisting-offline-capture-libraries --summary

# To inspect matched exported/imported names, without reading private data:
python3 research/nx300m_capture_elf_surface_audit.py \
  --root /path/to/preexisting-offline-capture-libraries

python3 research/test_nx300m_capture_elf_surface_audit.py
```

The tool invokes local `readelf -W` and `c++filt` to inspect ELF metadata only. It imposes file, size, symbol and subprocess time limits and never executes or distributes vendor code. Its output explicitly says camera-side execution, 1.14 identity and Picture Wizard EFL connection are **unverified**.

## Next required evidence before modifying capture or the UI

1. Authenticate the **exact original NX300M 1.14** firmware or an equivalent legitimate, independently verified extraction.
2. Identify the original UI executable/process and how it sends Picture Wizard commands into the Samsung capture library. Exported names do not reveal calling convention, parameter lifetime, or thread ownership.
3. Compare 1.14 and reference ELF hashes, dependencies, functions, relocations, and call sites. Do not reuse old 1.1 offsets based on matching function names.
4. Verify existing Picture Wizard parameter structure and camera-original JPEG/RAW capture path, including recovery and EXIF/MakerNotes invariants, **before** discussing a real hook.
5. Keep physical dial event mapping and camera firmware installation disabled until system-specific, safe read-only observations and full-brick recovery have been proven.

**Status: symbol evidence collected, original 1.14 ABI not yet available.**
