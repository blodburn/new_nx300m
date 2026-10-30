#ifndef NX300M_TIZEN_FILM_CONTROLLER_H
#define NX300M_TIZEN_FILM_CONTROLLER_H
#include "nx300m_film_menu.h"
#include <stddef.h>
/* Pure USERSPACE controller: no firmware address, device nodes or camera hooks.
 * Dial event mapping is supplied by a separately verified platform adapter.
 * Preview changes are never persisted until the explicit confirm event.
 */
enum nx_tizen_film_event {
 NX_TIZEN_FILM_OPEN=0,
 NX_TIZEN_FILM_ROTATE_CW=1,
 NX_TIZEN_FILM_ROTATE_CCW=2,
 NX_TIZEN_FILM_CONFIRM=3,
 NX_TIZEN_FILM_CANCEL=4
};
enum nx_tizen_film_result {
 NX_TIZEN_FILM_ERROR=-1,
 NX_TIZEN_FILM_NO_CHANGE=0,
 NX_TIZEN_FILM_CHANGED=1,
 NX_TIZEN_FILM_SAVED=2
};
typedef int (*nx_tizen_film_save_fn)(void *user,unsigned id);
typedef struct {
 unsigned committed_id;
 size_t preview_index;
 int open;
 nx_tizen_film_save_fn save;
 void *save_user;
} nx_tizen_film_controller;
typedef struct {
 unsigned committed_id, preview_id;
 const char *preview_name;
 const char *preview_description;
 const char *preceding_name;
 const char *following_name;
 size_t preview_index, count;
 int open, dirty;
} nx_tizen_film_view;
void nx_tizen_film_controller_init(
 nx_tizen_film_controller *ctrl,unsigned selected_id,
 nx_tizen_film_save_fn save,void *save_user);
int nx_tizen_film_dispatch(
 nx_tizen_film_controller *ctrl,enum nx_tizen_film_event event);
int nx_tizen_film_view_state(const nx_tizen_film_controller *ctrl,
                            nx_tizen_film_view *out);
/* Uses an explicit, caller-owned path in userspace. Host tests use tempdirs.
 * Atomic rename within the same filesystem; no hardware flash access.
 * Returns -1 on failure without replacing the destination. */
int nx_tizen_film_save_file(void *path_user,unsigned id);
#endif
