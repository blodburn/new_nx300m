# NX300M Picture Wizard — Capture menu value to DB setter static graph

**Reference only:** Existing private `di-camera-app-nx300` ARM ELF from modified MFW release 1.1, whose internal Samsung SLP version is **1.15**. This is **not** the camera owner's unmodified firmware **1.14**. No firmware binary is published, executed or patched.

## Confirmed static direct BL edges

```text
UI_Set_Capture_Menu_Info_By_GUI(tag_MENU_INFO)
    |
    +--- 2 BL ---> UI_Set_Capture_Menu_Value(eUI_VALUE_ITEM, int)
    |                 |
    |                 +--- 18 BL ---> UI_Set_Value(eUI_VALUE_ITEM, int)
    |                                      |
    +----------------- 2 BL --------------+
                                           |
                                           +--- 1 BL ---> UI_Set_Value_Capture_Menu
                                                             |
                                                             +--- 1 BL ---> UI_Get_DB_ID_Capture_Menu
                                                             |
                                                             +--- 1 BL ---> UI_Set_DB_Value_Capture_Menu
                                                                                 |
                                                                                 ?
                                                    Actual persistence/IPC/ISP: NOT VERIFIED
```

| Direct ARM BL source → destination | Reference callsite count |
|---|---:|
| Capture menu info → Capture menu value | 2 |
| Capture menu info → Generic set value | 2 |
| Capture menu value → Generic set value | 18 |
| Generic set value → Capture menu set value | 1 |
| Capture menu set value → Capture-menu DB ID lookup | 1 |
| Capture menu set value → Capture-menu DB value setter | 1 |
| **Total direct machine-level callsite matches** | **25** |

Six explicitly named functions and six edge groups are checked. The words **DB setter** name a symbol; they do **not** independently establish that a persistent database file was updated. Even though these edges form a graph, the callsite branches can be conditional or belong to different menu IDs. **No end-to-end live Picture Wizard execution has been demonstrated.**

## Important disassembly pitfall

The large `UI_Set_DB_Value_Capture_Menu(eDB_SYSTEM_MENU,int)` routine contains repetitive embedded lookup/switch data. A blind four-byte linear scan identifies a large number of BL-like bit patterns there, predominantly lacking corresponding function symbols. These must **not** be represented as hundreds of genuine nested calls. The new analyzer deliberately excludes the DB setter's **body** from call scanning. Its **entry point as a direct call target** from a separate bounded function is valid static evidence, but its internal runtime paths are left unproven.

## Offline reproduction

```sh
python3 research/nx300m_pw_capture_db_chain_audit.py \
  --elf /path/to/private/di-camera-app-nx300 --summary

python3 research/test_nx300m_pw_capture_db_chain_audit.py
```

The tool verifies ARM ELF32 EABI5 executable file-backed segments, resolves defined function symbols, and checks exact direct ARM-state BL targets only among the **four source functions** needed for this bounded graph. It never executes the binary or traverses blind DB switch data. Eight synthetic fixtures check six expected edges, incorrect targets, altered callsites, duplicate or missing symbols, function size limits, and false positive BL-like words inside DB data. The report marks `ui_picture_wizard_event_reaches_db_setter_verified=false`, `db_function_changes_persistent_storage_verified=false`, `camera_capture_ipc_or_isp_execution_verified=false`, `actual_nx300m_firmware_114_abi_verified=false`, and `flash_or_camera_memory_patch_permitted=false`.

## Remaining verification

1. Establish control-flow conditions and actual parameter IDs across `UI_Set_Capture_Menu_Value`, `UI_Set_Value`, `UI_Set_Value_Capture_Menu`, and `UI_Get_DB_ID_Capture_Menu`. The current paths are separate static callsite observations.
2. Prove actual persistence, external IPC dispatch and effect on the live-view/ISP/JPEG pipeline with **read-only reference evidence first**. The current UI ELF graph does not prove any hardware process received a message.
3. Obtain and authenticate the original NX300M **1.14** firmware, verify its internal SLP version and CRC, and repeat source-level and machine-code analysis for that exact build. No legacy numerical offsets may be reused.
4. Verify device-specific full-brick recovery and calibration preservation before any physical firmware modification.

**No installable modified firmware was created.**
