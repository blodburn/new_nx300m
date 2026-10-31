# NX300M Capture preference jump-table and PLT evidence

**Source and restrictions:** Read-only inspection of the existing private modified MFW release 1.1 research `di-camera-app-nx300` ELF. Its parent image's Samsung SLP header reports underlying firmware **1.15**, not the owner's **stock NX300M 1.14**. No manufacturer binaries, image execution, camera writes or firmware patches are published.

## Important correction to the previous DB graph

The earlier bounded call-graph audit explicitly declined to analyze the large `UI_Set_DB_Value_Capture_Menu(eDB_SYSTEM_MENU, int)` function because a linear four-byte scan returned many seemingly spurious BL instructions. **That caution was valid, but calling the entire area 'BL-like lookup data' was incomplete and potentially misleading.**

New examination of the exact ARM prologue proves the routine uses an **absolute-address dispatch table with 205 entries** (index 0..204 after decrementing the input). The entries are data; the **targets** point into executable case blocks. Many case blocks contain genuine direct ARM-state `BL` instructions to dynamic preference API PLT stubs.

```text
UI_Set_Value_Capture_Menu(eUI_VALUE_ITEM,int)
    ├── UI_Get_DB_ID_Capture_Menu(eUI_VALUE_ITEM,int)
    └── UI_Set_DB_Value_Capture_Menu(eDB_SYSTEM_MENU,int)
           |
           +-- index shift -1 + compare index<=204
           |
           +-- computed PC load from 205-entry jump table
                 |
                 +-- 192 simple case blocks ----> pref_set_long()
                 |
                 +-- 12 case entries ----------> default return
                 |
                 +-- 1 special block ----------> pref_set_long()
                                           |----> pref_get_long() x2
                                           |----> slpcam_print_info()
                                           +----> UI_Set_Value(...)
```

## Verified counts in modified 1.15 research reference

| Observation | Count / result |
|---|---:|
| Absolute jump-table entries | **205** |
| Distinct jump targets | **194** |
| Straight-line blocks calling `pref_set_long` | **192** |
| Default return table entries | **12** |
| Exceptional conditional case | **1** (table index 124, one-based) |
| All syntactic direct `BL` to `pref_set_long` | **193** |
| Direct `BL` to `pref_get_long` in special block | **2** |
| Direct `BL` to `slpcam_print_info` in special block | **1** |

The external function identities were matched to **`R_ARM_JUMP_SLOT` entries of `.rel.plt`**, not inferred from an unverified call address. A general linear disassembler cannot simply treat jump-table 32-bit addresses as instructions, but it also must not discard the valid executable case blocks that the table references.

The 192 simple case blocks contain 192 distinct local `r1` preference-key immediate values. Those are the source code's constants and **are not proven Picture Wizard setting IDs**. One exceptional block has conditional logic and additional getter/debug actions; its runtime execution is not shown.

### Reproducible read-only analysis

```sh
python3 research/nx300m_capture_pref_jump_table_audit.py \
  --elf /path/to/private/di-camera-app-nx300 --summary

python3 research/test_nx300m_capture_pref_jump_table_audit.py
```

The analyzer requires exact reference ARM32 EABI5 switch-prologue opcodes and verifies all 205 table addresses, classifies referenced case code, resolves direct calls through ELF `.rel.plt` symbols, and fails closed for unexpected layouts, missing symbol relocations, missing calls or malformed targets. Eight synthetic tests exercise the normal reference layout and reject changed selectors, invalid targets, PLT mismatches, altered BL code, altered exceptional calls and wrong default blocks.

## What this does NOT prove

- `pref_set_long` is a **preferences-setting API** referenced by machine code; an observed static `BL` does not prove it was invoked by a real Picture Wizard event, successfully persisted to storage or forwarded to the DRIMeIV image processor.
- The symbolic `eDB_SYSTEM_MENU` index is **not yet associated with a specific Picture Wizard preset** or an officially documented native setting ID. Jump-table case indices and preference-key constants are not the same as a Film Simulator look ID.
- Stock **NX300M 1.14** has not been authenticated/extracted or compared. The older modified 1.15 function addresses MUST NOT be used as camera hooks.
- Camera recovery and calibration safety have not been proven; therefore no installable firmware or experimental device patch is authorized.

**The earlier DB graph remains useful for six bounded caller-to-callee edges, but its discussion of skipped DB function code is superseded by this inspected jump-table analysis.**
