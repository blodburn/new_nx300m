#ifndef NX300M_FILM_KEYS_H
#define NX300M_FILM_KEYS_H
#include "nx300m_film_menu.h"
/* Candidate NX300-series Linux/X11 keycodes, not validated on NX300M hardware. */
enum { NX_KEY_UP=80, NX_KEY_LEFT=83, NX_KEY_RIGHT=85, NX_KEY_DOWN=88,
       NX_KEY_OK=104, NX_KEY_MENU=135, NX_KEY_FN=180, NX_KEY_EV=181 };
typedef struct {
    nx_film_menu selection;
    int open;
} nx_film_controller;
void nx_controller_init(nx_film_controller *controller);
const nx_film_preset *nx_controller_focused(const nx_film_controller *controller);
/* Returns 1 on OK, 2 on open/close, 0 on rotation/no-op, -1 on invalid. */
int nx_controller_key(nx_film_controller *c,unsigned key,const char *config_file);
#endif
