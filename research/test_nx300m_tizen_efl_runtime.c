/* Real EFL UI translation unit exercised end-to-end with a HOST-ONLY
 * in-process Evas/Elementary test double.
 * NO camera firmware or real EFL library is used.
 * Test calls the actual Evas key callback registered by the UI, verifies the
 * displayed preset, atomic commit/cancel and fail-closed input mapping.
 */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>

/* Include actual GUI code in test TU to inspect real controller state.
 * This does NOT provide, link or claim an NX300M Tizen EFL runtime. */
#define main nx300m_tizen_gui_entry_for_host_test
#include "nx300m_tizen_filmsim_efl.c"
#undef main

struct _Evas_Object { unsigned kind; char markup[4096]; };
struct _Evas {unsigned placeholder;};
static struct _Evas_Object mock_objects[24];
static size_t object_count;
static Evas_Object_Event_Cb registered_key;
static Evas_Smart_Cb registered_close;
static Evas_Object *registered_key_object;
static unsigned run_scenario;
static char config_filename[256];
static unsigned events_seen;
static void key(const char *name){
 Evas_Event_Key_Down event={name};
 assert(registered_key);
 registered_key(NULL,NULL,registered_key_object,&event);
 events_seen++;
}
static int matches_preset(unsigned id){
 nx_tizen_film_view v;
 assert(nx_tizen_film_view_state(&ui.controller,&v)==0);
 return v.preview_id==id;
}
static int saved_id(unsigned id){
 nx_film_menu mode;
 nx_film_menu_init(&mode);
 return nx_film_menu_load(&mode,config_filename)==0&&mode.selected_id==id;
}
int elm_init(int argc,char **argv){(void)argc;(void)argv;return 1;}
void elm_shutdown(void){}
void elm_exit(void){}
Evas_Object *elm_win_add(Evas_Object *parent,const char *name,int type){
 (void)parent;(void)name;(void)type;
 assert(object_count<24);
 Evas_Object *obj=&mock_objects[object_count++];
 obj->kind=1;
 return obj;
}
void elm_win_title_set(Evas_Object *win,const char *title){(void)win;(void)title;}
void elm_win_autodel_set(Evas_Object *win,int on){(void)win;(void)on;}
void elm_win_resize_object_add(Evas_Object *win,Evas_Object *obj){(void)win;(void)obj;}
Evas_Object *elm_box_add(Evas_Object *parent){
 (void)parent;assert(object_count<24);
 Evas_Object *obj=&mock_objects[object_count++];
 obj->kind=2;
 return obj;
}
void elm_box_horizontal_set(Evas_Object *box,int val){(void)box;(void)val;}
void elm_box_pack_end(Evas_Object *box,Evas_Object *child){(void)box;(void)child;}
Evas_Object *elm_label_add(Evas_Object *parent){
 (void)parent;assert(object_count<24);
 Evas_Object *obj=&mock_objects[object_count++];
 obj->kind=3;
 return obj;
}
void elm_object_text_set(Evas_Object *obj,const char *markup){
 assert(obj && obj->kind==3 && markup);
 size_t n=strlen(markup);
 assert(n<sizeof(obj->markup));
 memcpy(obj->markup,markup,n+1);
}
void evas_object_size_hint_weight_set(Evas_Object *obj,double x,double y){
 (void)obj;(void)x;(void)y;
}
void evas_object_size_hint_align_set(Evas_Object *obj,double x,double y){
 (void)obj;(void)x;(void)y;
}
void evas_object_smart_callback_add(Evas_Object *obj,const char *event,
                                    Evas_Smart_Cb cb,void *user){
 (void)obj;(void)user;
 if(strcmp(event,"delete,request")==0)registered_close=cb;
}
void evas_object_event_callback_add(Evas_Object *obj,int type,
                                    Evas_Object_Event_Cb cb,void *user){
 (void)user;
 assert(type==EVAS_CALLBACK_KEY_DOWN);
 registered_key=cb;registered_key_object=obj;
}
void evas_object_resize(Evas_Object *obj,int w,int h){
 assert(obj&&w==640&&h==360);
}
void evas_object_focus_set(Evas_Object *obj,int focused){
 assert(obj&&focused==EINA_TRUE);
}
void evas_object_show(Evas_Object *obj){assert(obj);}

void elm_run(void){
 assert(registered_key&&registered_close);
 assert(ui.sidebar&&ui.current&&ui.neighbors&&ui.status);
 assert(strstr(ui.current->markup,"Samsung Original"));
 assert(strstr(ui.sidebar->markup,"Samsung Original"));
 switch(run_scenario){
 case 0: /* Unconfigured UI must ignore generic and unknown keys. */
  assert(ui.keymap.enabled==0);
  key("Right");key("Left");key("Return");key("Escape");
  key("NX300M_UNKNOWN");
  assert(matches_preset(0)&&ui.controller.committed_id==0);
  assert(ui.controller.open&&events_seen==5);
  assert(access(config_filename,F_OK)!=0);
  assert(strstr(ui.status->markup,"KEY INPUT DISABLED"));
  break;
 case 1: /* Explicit desktop demo, then cancel of second change. */
  assert(ui.keymap.enabled);
  key("Right");
  assert(matches_preset(100)&&ui.controller.committed_id==0);
  assert(strstr(ui.current->markup,"Fuji PROVIA Study"));
  assert(strstr(ui.sidebar->markup,"Fuji PROVIA Study"));
  assert(!saved_id(100));
  key("Return");
  assert(saved_id(100));
  assert(ui.controller.committed_id==100&&!ui.controller.open);
  key("Right"); /* Must open new preview AFTER prior confirm. */
  assert(matches_preset(101)&&ui.controller.committed_id==100);
  key("Escape");
  assert(matches_preset(100)&&!ui.controller.open);
  assert(saved_id(100));
  key("Escape"); /* idempotent, must not open a new preview */
  assert(!ui.controller.open&&saved_id(100));
  break;
 case 2: /* Explicit camera-like mapping is not guessed. */
  assert(ui.keymap.enabled);
  key("Right");key("Return");
  assert(matches_preset(0)&&ui.controller.committed_id==0);
  key("RingCW");
  assert(matches_preset(100)&&ui.controller.committed_id==0);
  key("SaveMode");
  assert(saved_id(100)&&!ui.controller.open);
  key("RingCCW");
  assert(matches_preset(0)&&ui.controller.committed_id==100);
  key("CancelMode");
  assert(matches_preset(100)&&ui.controller.committed_id==100);
  assert(saved_id(100));
  break;
 case 3: /* Invalid/incomplete keymap never enables any event. */
  assert(!ui.keymap.enabled);
  key("RingCW");key("Right");key("Return");
  assert(matches_preset(0)&&ui.controller.committed_id==0);
  assert(access(config_filename,F_OK)!=0);
  break;
 case 4: /* No target settings path: confirmation cannot commit. */
  assert(ui.keymap.enabled);
  key("Right");
  key("Return");
  assert(ui.controller.committed_id==0&&ui.controller.open);
  assert(matches_preset(100)&&!saved_id(100));
  assert(strstr(ui.status->markup,"NOT SAVED"));
  break;
 case 5: /* Bounded keyname observations: no more than 32 log entries. */
  assert(!ui.keymap.enabled);
  for(unsigned j=0;j<42;j++)key("ReadOnlyKeyName");
  key("Invalid\nEscape");
  assert(ui.observed_keynames==32);
  assert(matches_preset(0)&&ui.controller.committed_id==0);
  break;
 default:assert(0&&"unknown scenario");
 }
}
static void reset_environment(void){
 unsetenv("NX_FILM_DEMO_KEYS");
 unsetenv("NX_FILM_KEY_CW");
 unsetenv("NX_FILM_KEY_CCW");
 unsetenv("NX_FILM_KEY_CONFIRM");
 unsetenv("NX_FILM_KEY_CANCEL");
 unsetenv("NX_FILM_LOG_KEYS");
 unsetenv("NX_FILM_CONFIG");
 memset(&ui,0,sizeof(ui));
 memset(mock_objects,0,sizeof(mock_objects));
 registered_key=NULL;registered_close=NULL;
 registered_key_object=NULL;
 object_count=0;events_seen=0;
}
static void run_case(unsigned scenario){
 reset_environment();
 run_scenario=scenario;
 if(scenario!=4)assert(setenv("NX_FILM_CONFIG",config_filename,1)==0);
 if(scenario==1||scenario==4)
  assert(setenv("NX_FILM_DEMO_KEYS","1",1)==0);
 if(scenario==2){
  assert(setenv("NX_FILM_KEY_CW","RingCW",1)==0);
  assert(setenv("NX_FILM_KEY_CCW","RingCCW",1)==0);
  assert(setenv("NX_FILM_KEY_CONFIRM","SaveMode",1)==0);
  assert(setenv("NX_FILM_KEY_CANCEL","CancelMode",1)==0);
 }
 if(scenario==3)assert(setenv("NX_FILM_KEY_CW","RingCW",1)==0);
 if(scenario==5)assert(setenv("NX_FILM_LOG_KEYS","1",1)==0);
 char *args[]={(char *)"nx300m-efl-host-test",NULL};
 assert(nx300m_tizen_gui_entry_for_host_test(1,args)==0);
 assert(registered_close);
 if(access(config_filename,F_OK)==0)assert(unlink(config_filename)==0);
}
int main(void){
 char dir[]="/tmp/nx300m-efl-runtime-XXXXXX";
 assert(mkdtemp(dir));
 int n=snprintf(config_filename,sizeof(config_filename),
                "%s/film.cfg",dir);
 assert(n>0&&(size_t)n<sizeof(config_filename));
 for(unsigned scenario=0;scenario<=5;scenario++)run_case(scenario);
 assert(rmdir(dir)==0);
 puts("PASS host EFL runtime simulation: 6 GUI scenarios, disabled default, committed sidebar display, explicit mapping, confirm/persist, cancel, error feedback, bounded diagnostics");
 return 0;
}
