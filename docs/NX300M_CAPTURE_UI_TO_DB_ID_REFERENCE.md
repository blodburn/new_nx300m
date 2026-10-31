# NX300M Capture UI-value → DB-ID switch evidence

**Reference:** Private `di-camera-app-nx300` ELF from modified MFW release 1.1, based on Samsung SLP **1.15**. **Stock camera firmware 1.14 is not obtained or verified.** Read-only extraction; do not execute, patch or flash camera firmware.

## Additional mapping layer after `pref_set_long` discovery

```text
Picture Wizard UI event
  |
  +--> GUI_Set_System_Value(r0,r1,r2,r3)
        | value and menu semantics NOT proven
        v
      UI_Set_Menu_Info_By_GUI
        | conditional Capture dispatch NOT proven for PW
        v
      UI_Set_Value_Capture_Menu(eUI_VALUE_ITEM,int)
        |
        v
      UI_Get_DB_ID_Capture_Menu(eUI_VALUE_ITEM,int)
        |
        +-- 209-item ARM absolute jump table, selector numeric range 3..211
             |
             +-- 102 default-zero return cases
             +--  89 direct immediate-return cases
             +--  16 helper-function call cases
             +--   2 conditional helper-function call cases
        |
        v
      UI_Set_DB_Value_Capture_Menu(eDB_SYSTEM_MENU,int)
        |
        +-- 205-entry jump table and 193 pref_set_long BL instructions
        v
      Actual PW key, runtime storage, native IPC/ISP: NOT VERIFIED
```

## Numeric index 39

The previous UI register audit observed the machine-level value `r2=39` at selected Picture Wizard state-handler callsites. In the **separate** `UI_Get_DB_ID_Capture_Menu` switch, **input numeric index 39** selects a code block that calls a local ARM helper. This is a **numeric coincidence and candidate cross-reference**, not a validated dataflow from that UI register into the DB-ID switch. It is not proof of a Picture Wizard-specific preference key, nor of a camera ISO/contrast/filter setting.

## Exact older-reference machine-code evidence

| Aspect | Verified result |
|---|---:|
| ARM jump table entries | **209** |
| Input numeric index range | **3 through 211** |
| Unique code-block targets | **108** |
| Default-zero returns | **102** |
| Constant-return blocks | **89** |
| Local helper-call blocks | **16** |
| Conditional local helper-call blocks | **2** |
| Numeric index 39 | **local helper-call block** |

The 209-entry switch uses an ARM computed PC load guarded by a compare with `208`, after subtracting `3` from the input. Helpers are not automatically mapped to symbolic Picture Wizard IDs; some local call targets lack standalone defined ELF function symbols.

## Reproduction

```sh
python3 research/nx300m_capture_ui_db_id_audit.py \
  --elf /path/to/private/di-camera-app-nx300 --summary

python3 research/test_nx300m_capture_ui_db_id_audit.py
```

The auditor reads an existing private ARM32 ELF, verifies the expected switch prologue and in-bounds 209-entry table, and conservatively classifies exact case forms. It explicitly marks Picture Wizard UI index, DB key mapping, native IPC, original firmware 1.14 ABI and device patch authorization **unverified / false**. Eight synthetic fixtures reject changed branch selectors, invalid targets, wrong helper instructions, altered default return and broken ELF/symlinks.

## Required before real integration

1. Trace the semantic `eUI_VALUE_ITEM` argument through the Picture Wizard-specific conditional UI path into `UI_Get_DB_ID_Capture_Menu` instead of joining unrelated numeric values.
2. Trace the helper's return to the `eDB_SYSTEM_MENU` selector and ultimately to the *exact* `pref_set_long` key, and distinguish preferences persistence from Capture IPC/ISP effects.
3. Obtain and authenticate original **NX300M 1.14** and independently verify exactly the same functions, tables and recovery path; no MFW 1.15 address is reusable on 1.14.

**This is read-only static progress, not a completed firmware integration.**
