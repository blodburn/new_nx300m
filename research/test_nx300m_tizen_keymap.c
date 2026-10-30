#include "nx300m_tizen_keymap.h"
#include "nx300m_tizen_film_controller.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct {unsigned id, count;} save_state;
static int save(void *context,unsigned preset){
 save_state *s=(save_state *)context;
 s->id=preset;s->count++;
 return 0;
}
static void test_map_validations(void){
 nx_tizen_keymap m;
 assert(nx_tizen_keymap_set(&m,"DIAL_CW","DIAL_CCW","OK","CANCEL")==0);
 assert(m.enabled);
 assert(nx_tizen_keymap_lookup(&m,"DIAL_CW")==NX_TIZEN_INPUT_CW);
 assert(nx_tizen_keymap_lookup(&m,"DIAL_CCW")==NX_TIZEN_INPUT_CCW);
 assert(nx_tizen_keymap_lookup(&m,"OK")==NX_TIZEN_INPUT_CONFIRM);
 assert(nx_tizen_keymap_lookup(&m,"CANCEL")==NX_TIZEN_INPUT_CANCEL);
 assert(nx_tizen_keymap_lookup(&m,"DIAL_NOT_INFERRED")==NX_TIZEN_INPUT_NONE);
 assert(nx_tizen_keymap_set(&m,"DIAL","DIAL","OK","CANCEL")==-1);
 assert(!m.enabled);
 assert(nx_tizen_keymap_lookup(&m,"DIAL")==NX_TIZEN_INPUT_NONE);
 assert(nx_tizen_keymap_set(&m,"CW","CCW","OK",NULL)==-1);
 assert(!m.enabled);
 assert(nx_tizen_keymap_set(&m,"CW","CCW","OK","/dev/input/event0")==-1);
 assert(!m.enabled);
 assert(nx_tizen_keymap_set(&m,"CW","CCW","OK","Escape\nINJECT")==-1);
 assert(!m.enabled);
 assert(nx_tizen_keymap_set(&m,"CW","CCW","OK","Escape\x1b")==-1);
 assert(!m.enabled);
 char longkey[NX_TIZEN_KEYNAME_MAX+1];
 memset(longkey,'A',sizeof(longkey)-1);
 longkey[sizeof(longkey)-1]=0;
 assert(nx_tizen_keymap_set(&m,longkey,"CCW","OK","CANCEL")==-1);
 assert(!m.enabled);
 assert(!nx_tizen_keyname_observable(""));
 assert(!nx_tizen_keyname_observable(NULL));
 assert(!nx_tizen_keyname_observable("KEY SPACE"));
 assert(nx_tizen_keyname_observable("XF86CameraPlus"));
 assert(nx_tizen_keyname_observable("Dial_1+"));
 nx_tizen_keymap_demo(&m);
 assert(nx_tizen_keymap_lookup(&m,"Right")==NX_TIZEN_INPUT_CW);
 assert(nx_tizen_keymap_lookup(&m,"Left")==NX_TIZEN_INPUT_CCW);
 assert(nx_tizen_keymap_lookup(&m,"Return")==NX_TIZEN_INPUT_CONFIRM);
 assert(nx_tizen_keymap_lookup(&m,"Escape")==NX_TIZEN_INPUT_CANCEL);
 assert(nx_tizen_keymap_lookup(&m,"Down")==NX_TIZEN_INPUT_NONE);
}
static void test_events_and_idempotence(void){
 nx_tizen_film_controller c;save_state state={0,0};
 nx_tizen_film_controller_init(&c,204,save,&state);
 nx_tizen_keymap map={0};
 /* Unknown and unconfigured events must never mutate film state. */
 assert(nx_tizen_keymap_lookup(&map,"Right")==NX_TIZEN_INPUT_NONE);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_OPEN)==NX_TIZEN_FILM_CHANGED);
 assert(nx_tizen_keymap_set(&map,"RING+","RING-","PRESS","BACK")==0);
 enum nx_tizen_input x=nx_tizen_keymap_lookup(&map,"RING+");
 assert(x==NX_TIZEN_INPUT_CW);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_ROTATE_CW)==NX_TIZEN_FILM_CHANGED);
 nx_tizen_film_view v;assert(nx_tizen_film_view_state(&c,&v)==0);
 assert(v.preview_id==0&&c.committed_id==204);
 assert(state.count==0);
 assert(nx_tizen_keymap_lookup(&map,"UNEXPECTED")==NX_TIZEN_INPUT_NONE);
 assert(c.committed_id==204);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CONFIRM)==NX_TIZEN_FILM_SAVED);
 assert(c.committed_id==0&&state.count==1&&state.id==0);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CONFIRM)==NX_TIZEN_FILM_NO_CHANGE);
 assert(state.count==1);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_OPEN)==NX_TIZEN_FILM_CHANGED);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CANCEL)==NX_TIZEN_FILM_CHANGED);
 assert(c.committed_id==0&&state.count==1);
}
int main(void){
 test_map_validations();test_events_and_idempotence();
 puts("PASS explicit 4-key mapping: unknown/invalid events ignored, injection rejected, disable-on-invalid, preview/confirm idempotence, no implicit camera key inference");
 return 0;
}
