#include "nx300m_film_keys.h"
void nx_controller_init(nx_film_controller *c){
    if(!c)return;
    nx_film_menu_init(&c->selection);
    c->open=0;
}
const nx_film_preset *nx_controller_focused(const nx_film_controller *c){
    return c?nx_film_by_id(c->selection.selected_id):NULL;
}
int nx_controller_key(nx_film_controller *c,unsigned key,const char *config_file){
    if(!c)return -1;
    if(key==NX_KEY_MENU){c->open=!c->open;return 2;}
    if(!c->open)return 0;
    if(key==NX_KEY_LEFT || key==NX_KEY_RIGHT){
        /* ONE circular sequence: Samsung -> all Fuji -> all Leica -> Samsung. */
        if(nx_film_menu_action(&c->selection,
           key==NX_KEY_RIGHT?NX_ACT_NEXT:NX_ACT_PREV)!=0)return -1;
        if(config_file && nx_film_menu_store(&c->selection,config_file)!=0)return -1;
        return 0;
    }
    if(key==NX_KEY_OK){
        if(!nx_controller_focused(c))return -1;
        if(config_file && nx_film_menu_store(&c->selection,config_file)!=0)return -1;
        return 1;
    }
    if(key==NX_KEY_FN){c->open=0;return 2;}
    /* No family/group selection or effect-strength operation. */
    return 0;
}
