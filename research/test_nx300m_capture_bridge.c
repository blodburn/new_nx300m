#include "nx300m_capture_bridge.h"
#include "nx300m_film_menu.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static unsigned char frame[192*128*3],initial[sizeof(frame)];
int main(void){
    for(unsigned i=0;i<sizeof(frame);i++)frame[i]=(unsigned char)(i*17+33);
    memcpy(initial,frame,sizeof(frame));
    nx_film_menu selection;nx_film_menu_init(&selection);
    selection.selected_id=201;
    assert(nx_film_menu_store(&selection,"outputs/TEST_capture_bridge.cfg")==0);
    assert(nx_capture_apply_saved_look("outputs/TEST_capture_bridge.cfg",
        NX_STILL_RAW_OR_UNKNOWN,frame,192*3,192,128)==NX_STILL_BYPASSED);
    assert(memcmp(frame,initial,sizeof(frame))==0);
    assert(nx_capture_apply_saved_look("outputs/TEST_capture_bridge.cfg",
        NX_STILL_SRGB_RGB888,frame,192*3,192,128)==NX_STILL_APPLIED);
    assert(memcmp(frame,initial,sizeof(frame))!=0);
    memcpy(frame,initial,sizeof(frame));
    assert(nx_capture_apply_saved_look("outputs/not_present_example.cfg",
        NX_STILL_SRGB_RGB888,frame,192*3,192,128)==NX_STILL_BYPASSED);
    assert(memcmp(frame,initial,sizeof(frame))==0);
    selection.selected_id=0;
    assert(nx_film_menu_store(&selection,"outputs/TEST_capture_bridge.cfg")==0);
    assert(nx_capture_apply_saved_look("outputs/TEST_capture_bridge.cfg",
        NX_STILL_SRGB_RGB888,frame,192*3,192,128)==NX_STILL_BYPASSED);
    assert(memcmp(frame,initial,sizeof(frame))==0);
    puts("PASS persisted film choice feeds still image RGB transform; original/RAW identical and missing config bypasses");
    return 0;
}
