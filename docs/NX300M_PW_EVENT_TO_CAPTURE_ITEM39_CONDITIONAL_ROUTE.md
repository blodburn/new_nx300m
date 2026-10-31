# NX300M Picture Wizard state handler → conditional Capture item 39

**Evidence scope:** private modified MFW release 1.1, with embedded Samsung NX300M **SLP 1.15**. This machine-code route is **not verified in the user's original NX300M 1.14**. The offline witness executes no firmware and makes no camera changes.

## Stronger evidence: these are not merely two unrelated numeric 39s

```text
CAPPGUIGadgetPWState::handle(ISAFEvent const*)
          |
          | Direct ARM BL with r0=5, r1=4, r2=39, r3=UNKNOWN
          v
GUI_Set_System_Value(int,int,int,int)
          | Copies four args to tag_MENU_INFO
          v
UI_Set_Menu_Info_By_GUI(tag_MENU_INFO*)
          |
          | Menu command 5 != 10
          | Consult UI_Get_Value(1008): dynamic result
          | State=30 leads to UI_Get_State(2)==7 guard
          | Additional branches exist and are conditional
          v    ONLY when relevant dispatch condition permits
UI_Set_Capture_Menu_Info_By_GUI(tag_MENU_INFO)
          | Menu command 5 -> switch entry 5
          | Third record field 39 becomes local item
          | Special-case checks: 44,202,3,22,8,7,187
          | 39 matches none; fallthrough loads item 39
          v
UI_Set_Capture_Menu_Value(eUI_VALUE_ITEM=39, int=UNKNOWN)
          |
          ? Runtime execution, preference persistence, native IPC / ISP
             NOT proven
```

This analysis **now verifies a single static, conditional route** from a particular Picture Wizard state-handler ARM callsite to a Capture-value call using item **39**. The previous report's evidence stopped at two numerically matching `39` observations; the new function-local machine-code checks demonstrate that the `r2=39` record field can be forwarded as the Capture item when the intervening dispatcher branches allow it.

## Exact boundaries of the claim

| Stage | What the older reference proves | What remains open |
|---|---|---|
| PW handler | Direct call with first three argument constants **5,4,39** | Fourth argument value and live event |
| Generic GUI setter | All four input registers copied into `tag_MENU_INFO`; direct call to menu dispatcher | Whether runtime state permits next dispatch |
| UI menu dispatcher | Command 5 takes non-10 path; consults `UI_Get_Value(1008)`; one conditional Capture branch uses `UI_Get_State(2)==7` | Actual global UI state during a real PW action |
| Capture menu dispatcher | Menu-command case 5; third field becomes item; item 39 bypasses seven alternate handling values | Runtime reachability through global condition |
| Capture-value callsite | Direct ARM BL to `UI_Set_Capture_Menu_Value` with item **39** | Actual `int` value, saved preference key and call success |
| Firmware 1.14 / ISP / JPEG | No direct evidence | ABI compatibility, camera recovery, native pixel processing |

**Important:** This is a **possible control-flow route**, not proof that the camera executed it. Do not reinterpret the existing `UI_Get_Value(37)` → DB 52..64 → `pref_set_long` 868/236..280 chain as a confirmed runtime path. The values, mode, storage and image effect are still unverified.

## Reproduce

```sh
python3 research/nx300m_pw_ui39_capture_route_audit.py \
  --elf /path/to/private/di-camera-app-nx300

python3 research/test_nx300m_pw_ui39_capture_route_audit.py
```

The analyzer verifies exact instruction words and **symbol-resolved direct ARM BL targets** across four function boundaries, field-copy opcodes, the dynamic state selector, conditional state guard, command-5 switch case, seven special-case comparisons and the Capture item forwarding call. It refuses changed reference instructions and never attempts a firmware patch. Eight synthetic tests cover a positive route plus altered menu item, callee, record copy, state condition, Capture dispatch, switch entry and forwarding target.

## Next required work

1. Establish the specific UI event and `UI_Get_Value(1008)` state that actually drive Picture Wizard into the Capture branch on firmware **1.14**.
2. Track the fourth GUI argument and the Capture-value handler for item **39**, including runtime value conversion, DB ID selection, `pref_set_long` result and later `pref_get_long` reads.
3. Verify the original **1.14** SLP archive's provenance and ELF ABI, then prove Capture IPC/ISP/JPEG behavior and safe full-brick recovery independently.

No installable firmware, sensor calibration changes, ISP writes or camera runtime hooks are included.
