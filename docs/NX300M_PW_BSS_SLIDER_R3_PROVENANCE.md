# NX300M Picture Wizard: slider-state data provenance

**Scope:** Offline static analysis of an older modified Samsung SLP 1.15 research ELF. These results are not validated on stock NX300M 1.14 or a physical camera.

## What is verified

- A Picture Wizard handler sends constants `(5, 4, 39)` and a variable fourth argument to the generic menu-setting function.
- A separate handler branch sends `(2, 4, 39, 0)`.
- The variable fourth argument is read from a writable, uninitialized ELF memory section. Slider increase, decrease and selection functions also use this state.
- Static examination identified 71 references: 48 immediate word reads, 18 immediate word writes and 5 references requiring further instruction tracing.

## Functional boundary

```text
Picture Wizard slider actions
          |
          v
Writable selection state (RAM)
          |
          v
Event argument 4 (dynamic) ---> Conditional Capture menu routing
          |                                   |
          v                                   v
Runtime value not observed          Actual event route unverified
                                               |
                                               v
                                 Preference / ISP effects unverified
```

These are machine-code references, not actual recorded operations or confirmation that a saved preference or image output changed.

## Reproduction

The read-only analyzer is `research/nx300m_pw_global_r3_provenance_audit.py` and eight synthetic unit tests are in `research/test_nx300m_pw_global_r3_provenance_audit.py`. The full host regression suite is run with `make test`.

## Pending checks

Verify the state value and menu conditions during an actual event, correlate the item with preference-setting calls, and independently authenticate the original firmware before any physical-camera experiment.
