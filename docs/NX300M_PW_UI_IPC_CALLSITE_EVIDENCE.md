# NX300M — Picture Wizard UI event → generic setter call evidence

**Read-only analysis.** The inspected `di-camera-app-nx300` ELF comes from the existing **MFW 1.1 modified research extraction (internal Samsung SLP version 1.15)**. These addresses and relationships have **not** been verified in the owner's stock NX300M **1.14** firmware. No device API is called or firmware patched.

## New evidence: direct ARM32 calls in the actual UI ELF

The previous study of `set_picture_wizard(int)` identified a 95-instruction routine with 13 local pointers but no visible call or nonstack memory write. This is **not evidence of active Picture Wizard state mutation**. Instead, a fresh read-only scan of symbol-defined executable function ranges found:

| Function / call relationship | Direct ARM BL callsites in the older ELF |
|---|---:|
| `CAPPGUIGadgetPWState::handle(ISAFEvent const*)` → `GUI_Set_System_Value(int,int,int,int)` | **11** |
| `CAPPGUIGadgetPWState::Set_PWSlider_Minus(int)` → `GUI_Set_System_Value(int,int,int,int)` | **3** |
| `CAPPGUIGadgetPWState::Set_PWSlider_Plus(int)` → `GUI_Set_System_Value(int,int,int,int)` | **3** |
| `CAPPGUIGadgetPWState::handle(...)` → `CAPPGUIGadgetView::set_gg_picture_wizard_focus(int)` | **2** |
| `CAPPGUIGadgetView::init(...)` → `CAPPGUIGadgetView::set_gg_picture_wizard()` | **1** |
| Any defined functions → `set_picture_wizard(int)` | **0 direct ARM BL** |
| Any defined functions → `UI_Get_MM_Picture_wizard(...)` | **0 direct ARM BL** |

**The focused static scanner matched 11 distinct UI-related function candidate types and 41 total BL edges between the selected group**. Generic `GUI_Set_System_Value` has many unrelated callers in the camera application; the listed counts are only the specific Picture Wizard UI sources.

These are direct machine instruction callsites, not proof of a specific **Picture Wizard parameter ID**, an actual write through Samsung capture IPC, a running camera UI, or an updated image. The main missing chain is:

```text
CAPPGUIGadgetPWState::handle(ISAFEvent const*)
     ├── (direct ARM BL) Set_PWSlider_* / set_gg_picture_wizard_focus
     └── (11 direct ARM BL calls) GUI_Set_System_Value(int,int,int,int)
                                       |
                                       v
                           Parameter IDs / semantic routing
                                NOT YET PROVEN
                                       |
                                       v
                       Capture subsystem and Picture Wizard
                                NOT YET PROVEN
                                       |
                                       v
                       DRIMeIV ISP, Live View, JPEG/RAW
                                NOT YET PROVEN
```

## How to repeat offline

```sh
python3 research/nx300m_pw_ui_bl_call_audit.py \
  --elf /path/to/private/di-camera-app-nx300 --summary
python3 research/test_nx300m_pw_ui_bl_call_audit.py
```

The auditor only reads the private ELF, validates little-endian **ARM ELF32 EABI5**, examines executable file-backed `PT_LOAD` segments and defined `FUNC` symbol sizes, and decodes **direct ARM-state `BL` instructions**. It does not follow virtual/indirect calls, dynamic linker stubs, computed jumps, Thumb-mode instructions or IPC; therefore, a missing edge is **not** proof that no relationship exists. It does not publish the proprietary ELF. Eight synthetic fixture tests check ARM BL forward/backward offsets, noncall rejection, bounds, ELF headers, symbols, and fail-closed input handling.

## Required next check

1. Identify each `GUI_Set_System_Value` call's argument values or control-flow conditions in the *Picture Wizard UI state*, not generic menus; compare against `UI_Get_MM_Picture_wizard` and `GetPictureWizardParameter` with the same source evidence.
2. Trace its downstream native IPC dispatcher and distinguish UI-only state changes from actual native image/ISP parameter writes.
3. Acquire an authenticated, original **1.14** firmware extraction, verify the SLP header and all CRCs, then repeat BL callsite, function-body hash and parameter-layout analysis in **1.14**. Never reuse this modified 1.15 reference's numerical addresses as 1.14 hooks.
4. Verify RAW/Exif original paths, safe runtime access and full-brick recovery independently before considering on-camera execution.

**No new firmware binary, flashable package, firmware offset patch or on-device integration was produced.**
