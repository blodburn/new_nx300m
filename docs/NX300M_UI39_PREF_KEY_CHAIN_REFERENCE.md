# NX300M reference UI numeric item 39 → DB selector → pref_set_long key

**Scope:** Existing private modified MFW release 1.1 / underlying Samsung NX300M SLP **1.15**. **NOT** an authenticated original NX300M **1.14**, and no proof that the Picture Wizard UI actually sends numeric item `39` to this selector. Offline evidence only; no image execution, runtime patch, firmware flashing or vendor binary publication.

## Static mapping now observed

```text
UI_Get_DB_ID_Capture_Menu(eUI_VALUE_ITEM,int)
  |
  +-- numeric UI selector 39
         | direct ARM BL to a local helper
         v
       UI_Get_Value(37)
         |
         +-- result 1..12 (computed ARM jump table)
         |       1 -> DB selector 53 -> pref_set_long local key 236
         |       2 -> DB selector 54 -> pref_set_long local key 240
         |       ...
         |      12 -> DB selector 64 -> pref_set_long local key 280
         |
         +-- other result -> DB selector 52 -> pref_set_long local key 868
         |
         v
       Actual Picture Wizard key and capture IPC/ISP: NOT proven
```

An immediate `mov r0,#37` in the helper precedes a direct ARM BL to `UI_Get_Value(eUI_VALUE_ITEM)`. Its result is decremented by one and unsigned-compared with eleven. A 12-entry absolute jump table returns contiguous DB selector integers 53 through 64 for result values 1 through 12; everything outside the table takes the default return 52. Those selected DB values were independently joined to the **205-case preference setter table** verified in `nx300m_capture_pref_jump_table_audit.py`, rather than guessed from matching numbers.

## Reference-only preference key map

| `UI_Get_Value(37)` result | DB selector | `pref_set_long` local r1 key |
|---|---:|---:|
| Other than 1..12 | 52 | 868 |
| 1 | 53 | 236 |
| 2 | 54 | 240 |
| 3 | 55 | 244 |
| 4 | 56 | 248 |
| 5 | 57 | 252 |
| 6 | 58 | 256 |
| 7 | 59 | 260 |
| 8 | 60 | 264 |
| 9 | 61 | 268 |
| 10 | 62 | 272 |
| 11 | 63 | 276 |
| 12 | 64 | 280 |

These are local numerical constants from **one modified 1.15 research build**. They are **not verified Samsung public preference API contracts, Picture Wizard mode numbers, Fujifilm/Leica Film Simulator IDs or target 1.14 ABI mappings**. The fact that another UI register audit observed an immediate value `39` does not prove that its actual argument is used as the `eUI_VALUE_ITEM` selector of the DB-ID resolver.

## Reproduction

```sh
python3 research/nx300m_ui39_pref_key_chain_audit.py \
  --elf /path/to/private/di-camera-app-nx300 --summary

python3 research/test_nx300m_ui39_pref_key_chain_audit.py
```

The new read-only checker verifies the 209-entry UI DB-ID lookup, the *exact* helper call to `UI_Get_Value(37)`, all 12 branch-table targets, each selector return code, the default return, and the existing **205-entry preference switch's checked key values**. If any instruction pattern or preference key changes, it refuses the reference match; it does not silently apply a 1.15 address to another build. Eight synthetic tests reject corrupted input, altered lookup, missing/duplicate keys, wrong call address and invalid return branches. The user-owned firmware remains untouched.

## Remaining blockers

1. Establish a **runtime-reachable, parameter-traced** route from the Picture Wizard event and `GUI_Set_System_Value` to the actual numeric UI selector, without assuming that the register value `39` is the same item.
2. Verify that the selected preference key is read and used by the capture subsystem and exact native IPC/ISP processing, rather than stored as an unrelated menu option.
3. Obtain and authenticate original Samsung NX300M **1.14**, compare specific callsite machine code and value encodings, and independently establish a complete device recovery method before any on-device experiment.

**No installable firmware, hook offsets, or camera modifications are produced.**
