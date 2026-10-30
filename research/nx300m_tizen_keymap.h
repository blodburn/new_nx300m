#ifndef NX300M_TIZEN_KEYMAP_H
#define NX300M_TIZEN_KEYMAP_H
#include <stddef.h>
/* User-space EFL keyname -> preview action. Strict explicit mapping;
 * DOES NOT prove NX300M firmware 1.14 hardware-dial event names.
 * All inputs must be valid bounded single keyname tokens.
 */
enum nx_tizen_input {
 NX_TIZEN_INPUT_NONE=0,
 NX_TIZEN_INPUT_CW=1,
 NX_TIZEN_INPUT_CCW=2,
 NX_TIZEN_INPUT_CONFIRM=3,
 NX_TIZEN_INPUT_CANCEL=4
};
enum { NX_TIZEN_KEYNAME_MAX=48, NX_TIZEN_LOG_LIMIT=32 };
typedef struct {
 char cw[NX_TIZEN_KEYNAME_MAX];
 char ccw[NX_TIZEN_KEYNAME_MAX];
 char confirm[NX_TIZEN_KEYNAME_MAX];
 char cancel[NX_TIZEN_KEYNAME_MAX];
 int enabled;
} nx_tizen_keymap;
/* Fail closed: four distinct, nonempty, ASCII key tokens required.
 * No partial defaults, overlapping mappings, or malformed control chars.
 */
int nx_tizen_keymap_set(nx_tizen_keymap *m,const char *cw,
                         const char *ccw,const char *confirm,
                         const char *cancel);
/* Desktop-only demonstration; NEVER represents verified camera mapping. */
void nx_tizen_keymap_demo(nx_tizen_keymap *m);
enum nx_tizen_input nx_tizen_keymap_lookup(
 const nx_tizen_keymap *m,const char *keyname);
/* Filter event name for opt-in local stderr observation: ASCII [A-Za-z0-9_-+].
 * Does NOT read /dev/input or record device IDs, serials or raw key codes. */
int nx_tizen_keyname_observable(const char *keyname);
#endif
