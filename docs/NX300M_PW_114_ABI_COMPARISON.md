# NX300M firmware 1.14 — Picture Wizard ABI comparison gate

## Source availability (2026-10-30)

- An **unofficial, openly indexed Samsung NX preservation mirror** lists `NX300M_FW_v1.14.zip` (about 234 MB, archive timestamp 2014-10-12): https://nxfiles.nx.tc/files/NX300M/Firmware/.
- Exact indexed file URL: https://nxfiles.nx.tc/files/NX300M/Firmware/NX300M_FW_v1.14.zip.
- Softpedia also records version 1.14 from 2014-10-13. Samsung's current support page primarily lists the newer 1.15 package.
- The archive was **not downloaded or opened in the current development environment**: outbound retrieval requires separate approval. Listing a file does NOT certify original bytes, version identity or safe flashing.
- Do not check Samsung firmware binaries, extracted .so objects, device-unique calibration, or image samples into this public GitHub repository.

## Verified existing research reference

The existing private research workspace contains `nx300m/analysis/capture_libs/libcapture-fw-slpcam-nx300.so`, extracted from an older research firmware. The read-only ELF program-header and dynamic-symbol inspection confirms **ARM ELF32 EABI5**, and the following exact method bodies are mapped into valid file-backed load segments:

| Symbol | Reference body bytes |
|---|---:|
| `CProcessParameter::GetPictureWizardMode()` | 96 |
| `CProcessParameter::GetPictureWizardParameter(CProcessParameter::T_PWPARAM&)` | 172 |
| `CProcessParameter::updatePictureWizardBracket()` | 1036 |
| `CCapCmdIf::setPictureWizardBracket(int, int, int)` | 924 |

Cryptographic SHA-256 values are calculated for each mapped function body, in addition to the full ELF file hash. The unpublished reference has NOT been proven to match the owner's camera 1.14.

## Compare two locally available, separately verified ELF extractions

1. Acquire an original 1.14 firmware archive via an authorized source and record the SHA-256 before unpacking. Validate that its ZIP members and internal package metadata identify the exact model and version. Do **not** apply it to the camera.
2. Extract and identify the corresponding `libcapture-fw-slpcam-nx300.so` offline with the pre-existing, reviewed firmware unpacker. The research project already contains an original extraction but it is not confirmed as 1.14.
3. Run only the read-only comparison below:

```sh
python3 research/nx300m_picture_wizard_abi_gate.py \
  --reference-lib /path/to/older-research/libcapture-fw-slpcam-nx300.so \
  --candidate-lib /path/to/authenticated-1.14/libcapture-fw-slpcam-nx300.so
```

Outcomes are `BODY_BYTES_IDENTICAL`, `BODY_BYTES_DIFFER`, or `MISSING`. **A match is evidence about four function bodies only**, not proof that surrounding call sites, relocations, build configuration, structs, IPC messages, parameter lifetimes or firmware versions match. The tool intentionally sets `safe_to_reuse_reference_addresses=false` and `safe_to_flash_or_hook=false`, even when all four bodies are byte-identical.

## Legacy call-flow evidence to verify again in 1.14

An earlier Ghidra checkpoint `picture_wizard_native_trace.json` describes the original reference only:

```text
Captured control state
  CProcessParameter::GetPictureWizardMode()
    ├── CIpcProcess::SetIpcsIQParamCallBackFunction()
    └── CCapImageSetCb::makeNoteInfoConvert(...)
             └── original Exif/MakerNotes path

  CProcessParameter::createSnapshot()
    ├── updatePW()
    └── updatePictureWizardBracket()

  CLiveviewNodeIPCparameter::Prepare()
    └── setImageParameter()

  CRecipeStill::CreatePath(...)
    └── CRecipeStillSetting::GetEffectPathValue()
```

The same older analysis reports `user_param_id=16`, a mode-selector expression `mode OR 0x100`, and **12 native Picture Wizard dispatch choices**. The Film Simulator project currently has **13 fixed presets including Samsung Original**, so its preset IDs must **never** be interpreted as the original Samsung Picture Wizard native IDs without a verified translation and compatibility analysis.

## Current gate state

| Gate | State |
|---|---|
| Original 1.14 archive listed | Yes, unofficial mirror |
| 1.14 ZIP download and SHA-256 obtained | **No** |
| 1.14 embedded library located and analyzed | **No** |
| 1.1 research four-function fingerprints produced | **Yes** |
| Pairwise 1.1–1.14 code/ABI comparison | **Blocked: missing authenticated 1.14 local input** |
| Native screen + physical dial + capture hook | **Unverified** |
| Full-brick recovery and device calibration backup | **Unverified** |

**Do not flash firmware or reinterpret historical addresses as valid on 1.14.**
