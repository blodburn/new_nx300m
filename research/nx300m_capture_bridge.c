#include "nx300m_capture_bridge.h"
#include "nx300m_film_menu.h"
int nx_capture_apply_saved_look(const char *config_path,nx_still_format format,
                               unsigned char *pixels,size_t stride,
                               unsigned width,unsigned height){
    if(!config_path)return NX_STILL_INVALID;
    nx_film_menu active;
    nx_film_menu_init(&active);
    if(nx_film_menu_load(&active,config_path)!=0){
        /* No camera menu config: keep camera's original colors. */
        return nx_still_filter_inplace(0,format,pixels,stride,width,height);
    }
    return nx_still_filter_inplace(active.selected_id,format,pixels,stride,width,height);
}
