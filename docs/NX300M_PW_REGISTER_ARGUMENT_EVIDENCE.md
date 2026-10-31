# NX300M — Picture Wizard ARM r0–r3 menu argument evidence

**Static, read-only research on the older modified MFW 1.1 image (embedded Samsung SLP 1.15), NOT the owner's original NX300M 1.14.** No flash, no device execution and no executable proprietary bytes published.

## Verified direct-call path

```text
CAPPGUIGadgetPWState::handle(...)
           │ 11 ARM direct BL callsites
           ├───────────────────────────┐
           ▼                           │
GUI_Set_System_Value(r0,r1,r2,r3) ◄────┘
           │ copied as 4 fields to tag_MENU_INFO
           │ 1 direct BL
           ▼
UI_Set_Menu_Info_By_GUI(tag_MENU_INFO*)
           │ 2 static direct BL callsites (runtime branching NOT proven)
           ▼
UI_Set_Capture_Menu_Info_By_GUI(tag_MENU_INFO)
           │
           ▼
Original capture IPC / ISP: NOT verified
```

Additional source functions: `CAPPGUIGadgetPWState::Set_PWSlider_Minus(int)` and `Set_PWSlider_Plus(int)` each directly call `GUI_Set_System_Value` three times; `onEnter()` calls it once. These are **18 callsites in the four selected Picture Wizard UI functions**. The general setter and menu dispatcher also service settings unrelated to Picture Wizard. A static direct call in a conditional branch does not establish an executed event-to-ISP path.

## Only syntactic immediate constants established at these 18 callsites

| ARM register r0 | ARM register r1 | Callsite count |
|---:|---:|---:|
| 4 | 4 | 12 |
| 11 | 4 | 3 |
| 2 | 4 | 1 |
| 5 | 4 | 1 |
| 7 | 4 | 1 |

At specific callsites, `r2` immediately receives `39` (`0x27`), `38` (`0x26`), `13`, `2`, or `1`; where the register is loaded or computed dynamically it is **unknown**. A `mvn r3,#0` gives an unsigned 32-bit `0xFFFFFFFF` in some slider callsites; this is a machine register value, not a proven semantic meaning. These immediate constants are NOT authenticated Samsung parameter IDs, valid preset IDs or a validated real camera control interface.

## Read-only tool and tests

```sh
python3 research/nx300m_pw_setvalue_arg_audit.py \
  --elf /path/to/private/di-camera-app-nx300

python3 research/test_nx300m_pw_setvalue_arg_audit.py
```

The analyzer invokes the previous, bounded ARM ELF32 EABI5 validator, decodes direct `BL` instructions in defined function ranges and reads nearby ARM instructions for local `r0..r3` `mov`/`mvn` immediates. Register writes from `LDR`, arithmetic, conditional instructions, `MOV` register, unmodeled instructions, calls and block boundaries are **not** given invented constants. The report explicitly marks these as syntactic observations and sets `actual_picture_wizard_parameter_id_verified=false`, `capture_ipc_or_isp_execution_verified=false`, `firmware_114_abi_verified=false`, `device_write_or_flash_authorized=false`.

Eight synthetic unit cases test forward/negative ARM immediate patterns, r0–r3 constant reconstruction, unknown/written registers, boundary handling, invalid source, three-hop call graphs, and forbidding firmware compatibility claims. The private complete callsite manifest and original Samsung ELF remain outside the public repository.

## Remaining evidence

1. Inspect the switch and conditional branches in `UI_Set_Menu_Info_By_GUI`, proving which `tag_MENU_INFO` fields route to `UI_Set_Capture_Menu_Info_By_GUI` for Picture Wizard rather than other UI menu items.
2. Follow the capture dispatcher into actual IPC parameter transfer, including the exact setter ID, value encoding, thread and callback ordering, and confirm EXIF/RAW remains untouched.
3. Re-run the same analysis against authenticated **original NX300M 1.14 firmware**, not the modified 1.15 reference, and compare exact symbol bodies and callers. These reference addresses must NOT be reused in 1.14.
4. Confirm safe complete camera recovery before on-device experimental processing. No installable firmware is provided.
