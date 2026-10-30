#ifndef NX_FILM_MENU_H
#define NX_FILM_MENU_H
#include <stddef.h>
#include "nx300m_look_builder.h"
enum { NX_FAMILY_ORIGINAL=0, NX_FAMILY_FUJI=1, NX_FAMILY_LEICA=2 };
typedef struct {
    unsigned id;
    unsigned family;
    const char *name;
    const char *description;
    /* Own experimental rendering parameters; not recovered Fuji/Leica firmware values. */
    float saturation, shadow, highlight, gamma;
    float channel_mix[9];
} nx_film_preset;
typedef struct {
    unsigned selected_id;
    unsigned page;
    unsigned cursor;
} nx_film_menu;
enum nx_film_action { NX_ACT_PREV=0, NX_ACT_NEXT=1, NX_ACT_SELECT=2, NX_ACT_BACK=3 };
#define NX_FILM_MENU_VERSION 2
/* Single model of reference for Leica study presets; NOT a claim of original Leica calibration. */
#define NX_LEICA_REFERENCE_MODEL "Q3"
size_t nx_film_count(void);
const nx_film_preset *nx_film_by_index(size_t index);
const nx_film_preset *nx_film_by_id(unsigned id);
void nx_film_menu_init(nx_film_menu *menu);
int nx_film_menu_action(nx_film_menu *menu, enum nx_film_action action);
int nx_film_menu_store(const nx_film_menu *menu, const char *path);
int nx_film_menu_load(nx_film_menu *menu, const char *path);
int nx_film_lut_for_menu(const nx_film_menu *menu, nx_rgb12 *lut);
#endif
