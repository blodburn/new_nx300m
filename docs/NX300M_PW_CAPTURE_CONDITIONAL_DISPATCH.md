# NX300M Picture Wizard → Capture menu guarded branch evidence

**Scope:** Existing private modified MFW 1.1 research image, whose internal SLP header identifies Samsung NX300M firmware **1.15**. This is NOT the user's original stock **1.14**. It is a read-only static analysis; no vendor binaries, actual firmware modifications, camera memory reads or hardware calls are published.

## What is now proven within the older reference

```text
CAPPGUIGadgetPWState::handle(event)
                  |
          GUI_Set_System_Value(r0,r1,r2,r3)
                  |  copies four arguments to tag_MENU_INFO
                  v
          UI_Set_Menu_Info_By_GUI(record)
                  |
      +-----------+---------------------+
      |                                 |
      v                                 v
  Conditional branch A            Conditional branch B
  UI_Get_State(2) == 7?           two signed comparisons
    |                             record value vs 899 / 950
    | yes                         and zero-byte flag test
    v                                 | gated
  UI_Set_Capture_Menu_Info_By_GUI(record)
                  |
             Capture IPC / ISP
                  ?  NOT proven
```

**Two distinct direct ARM `BL` instructions targeting `UI_Set_Capture_Menu_Info_By_GUI` were observed inside `UI_Set_Menu_Info_By_GUI`. Both occur behind branch logic; neither is an unconditional Picture Wizard setting update.**

### Branch A: UI state check

The first witnessed local instruction sequence sets `r0 = 2`, directly calls `UI_Get_State(eUI_STATE_ITEM)`, compares its return value to `7`, converts the comparison to a boolean, and branches **past** the capture-menu call when the boolean is false. This is a static ARM instruction observation. Neither selector `2` nor state `7` has a verified semantic name for Picture Wizard, and nothing establishes that an actual PW event yields that state.

### Branch B: signed range and byte flag

The second capture-menu call is preceded by a comparison of a local record field to the immediate **899** (`0x383`) and **950** (`0x3B6`), conditional `BLE` branches, and a byte flag compared to zero. The recorded instructions contain a conditional branch to the capture-menu call when that flag is zero on one path; another branch calls the common-menu handler instead. The record field's meaning and all upstream control-flow conditions are **unverified**. The numeric thresholds are not known Picture Wizard IDs or film preset IDs.

| Question | Current verified status |
|---|---|
| Does UI PW handling call generic system-value setter? | Yes, direct static ARM BL in modified reference |
| Does generic setter call menu dispatcher? | Yes, direct static ARM BL in modified reference |
| Are there two capture-menu callsites in dispatcher? | Yes |
| Are both callsites guarded by conditionals? | Yes; exact instruction patterns verified |
| Is the runtime branch taken for a PW event? | **Not proven** |
| Are the state selector and range values documented Samsung Picture Wizard IDs? | **Not proven** |
| Does capture IPC/ISP/JPEG/RAW change? | **Not proven** |
| Is any of this byte-identical to original 1.14? | **Not proven** |

## Reproduce (private ELF only)

```sh
python3 research/nx300m_pw_capture_branch_audit.py \
  --elf /path/to/private/di-camera-app-nx300

python3 research/test_nx300m_pw_capture_branch_audit.py
```

The analyzer verifies ARM32 EABI5 load segments, resolves defined symbols and direct `BL` calls, then checks specific local instruction sequences **relative to each callsite**. It never treats a matching body as safe to execute on a camera. Eight synthetic unit tests check two positive branch witnesses and reject changed comparisons, changed state callee, failed branch skip and altered byte flags. The private full callsite manifest stays outside the public GitHub repository.

## Next actual blocker

Read the original **1.14** firmware with manufacturer-assessable provenance; then verify exact `UI_Set_Menu_Info_By_GUI` and `UI_Get_State` branch behavior in that version and follow `UI_Set_Capture_Menu_Info_By_GUI` into the native parameter IPC. Do not reuse the modified 1.15 addresses or assume this static menu dispatcher alters live image pixels. Independently verify complete recovery before any device installation.
