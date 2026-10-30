/*
 * NX300M Film Simulator — EFL/Elementary USERSPACE research UI.
 *
 * NOT installed in Picture Wizard; no camera live-view/ISP/JPEG hook.
 * Physical NX300M dial event keynames have NOT been verified on firmware 1.14.
 * Default input mapping is DISABLED until four explicit names are provided.
 * Desktop demo keys require opt-in NX_FILM_DEMO_KEYS=1.
 * Optional bounded observed-key logging requires NX_FILM_LOG_KEYS=1.
 * NO prev/next on-screen buttons, no intensity slider, no camera patch.
 * This file requires the matching ARM/Tizen EFL sysroot to build for camera.
 */
#include <Elementary.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nx300m_tizen_film_controller.h"
#include "nx300m_film_menu.h"
#include "nx300m_tizen_keymap.h"

typedef struct {
 Evas_Object *window,*root,*focus,*sidebar,*current,*neighbors,*status;
 nx_tizen_film_controller controller;
 nx_tizen_keymap keymap;
 unsigned observed_keynames;
 int log_keynames;
 const char *settings_path;
} film_ui;
static film_ui ui;

static int persist(void *context,unsigned id){
 return nx_tizen_film_save_file(context,id);
}
static void redraw(const char *message){
 nx_tizen_film_view v;
 if(nx_tizen_film_view_state(&ui.controller,&v)!=0)return;
 char text[1024],list[2048];
 snprintf(text,sizeof(text),
  "<align=center><color=#c99e69>FILM SIMULATOR  %zu/%zu</color><br/>"
  "<b><font_size=24>%s</font_size></b><br/>%s</align>",
  v.preview_index+1,v.count,v.preview_name,v.preview_description);
 elm_object_text_set(ui.current,text);
 size_t used=0;
 list[0]=0;
 for(int k=-2;k<=2;k++){
  const size_t at=(v.preview_index+v.count+(size_t)(k+13))%v.count;
  const nx_film_preset *p=nx_film_by_index(at);
  if(!p)continue;
  int n=snprintf(list+used,sizeof(list)-used,
   "%s%s%02zu %s%s",
   k==0?"<color=#e8b967><b>":"<color=#a8b1b9>",
   k==0?"&#9656; ":"",at+1,p->name,
   k==0?"</b></color><br/>":"</color><br/>");
  if(n<0||(size_t)n>=sizeof(list)-used)break;
  used+=(size_t)n;
 }
 elm_object_text_set(ui.sidebar,list);
 snprintf(text,sizeof(text),
  "<align=center>ROTATE: PREVIEW  |  CONFIRM: APPLY  |  BACK: CANCEL<br/>"
  "%s</align>",
  v.dirty?"NOT SAVED":"CURRENT MODE");
 elm_object_text_set(ui.neighbors,text);
 elm_object_text_set(ui.status,message?message:
   (!ui.keymap.enabled?
   "KEY INPUT DISABLED: SET ALL FOUR NX_FILM_KEY_* VARIABLES"
   :"OFFLINE TIZEN UI ONLY: NO CAMERA LIVEVIEW/ISP/JPEG CONNECTION"));
}
static void setup_input_mapping(void){
 memset(&ui.keymap,0,sizeof(ui.keymap));
 ui.log_keynames=getenv("NX_FILM_LOG_KEYS")&&
                  strcmp(getenv("NX_FILM_LOG_KEYS"),"1")==0;
 const char *demo=getenv("NX_FILM_DEMO_KEYS");
 if(demo&&strcmp(demo,"1")==0){
  nx_tizen_keymap_demo(&ui.keymap);
  fprintf(stderr,"NX300M: desktop-only demonstration key mapping enabled\n");
  return;
 }
 const char *cw=getenv("NX_FILM_KEY_CW");
 const char *ccw=getenv("NX_FILM_KEY_CCW");
 const char *confirm=getenv("NX_FILM_KEY_CONFIRM");
 const char *cancel=getenv("NX_FILM_KEY_CANCEL");
 if(cw||ccw||confirm||cancel){
  if(nx_tizen_keymap_set(&ui.keymap,cw,ccw,confirm,cancel)!=0)
   fprintf(stderr,"NX300M: incomplete/ambiguous keymap rejected; keys disabled\n");
 }
}
static void on_key_down(void *data,Evas *evas,Evas_Object *object,void *info){
 (void)data;(void)evas;(void)object;
 Evas_Event_Key_Down *ev=(Evas_Event_Key_Down *)info;
 if(!ev||!ev->keyname)return;
 if(ui.log_keynames && ui.observed_keynames<NX_TIZEN_LOG_LIMIT &&
    nx_tizen_keyname_observable(ev->keyname)){
  /* Observes only a bounded EFL key token. No device IDs, passwords,
   * camera storage, raw scancodes or Linux input device access. */
  fprintf(stderr,"NX_FILM_EFL_KEYNAME=%s\n",ev->keyname);
  ui.observed_keynames++;
 }
 enum nx_tizen_film_event event;
 switch(nx_tizen_keymap_lookup(&ui.keymap,ev->keyname)){
 case NX_TIZEN_INPUT_CW:
  event=NX_TIZEN_FILM_ROTATE_CW;
  break;
 case NX_TIZEN_INPUT_CCW:
  event=NX_TIZEN_FILM_ROTATE_CCW;
  break;
 case NX_TIZEN_INPUT_CONFIRM:
  event=NX_TIZEN_FILM_CONFIRM;
  break;
 case NX_TIZEN_INPUT_CANCEL:
  event=NX_TIZEN_FILM_CANCEL;
  break;
 default:
  return; /* unknown camera key event is ignored, not guessed */
 }
 /* A fresh rotation re-opens preview after a prior confirm/cancel; neither
  * confirm nor cancel silently re-opens the menu or changes a saved mode. */
 if(!ui.controller.open &&
    (event==NX_TIZEN_FILM_ROTATE_CW||event==NX_TIZEN_FILM_ROTATE_CCW))
  (void)nx_tizen_film_dispatch(&ui.controller,NX_TIZEN_FILM_OPEN);
 int result=nx_tizen_film_dispatch(&ui.controller,event);
 if(result==NX_TIZEN_FILM_SAVED)
  redraw("SAVED CONFIG ONLY: NATIVE JPEG ENGINE NOT CONNECTED");
 else if(result==NX_TIZEN_FILM_ERROR)
  redraw("NOT SAVED: CHECK EXPLICIT NX_FILM_CONFIG FILE PATH");
 else redraw(NULL);
}
static Evas_Object *make_label(Evas_Object *win,Evas_Object *parent){
 Evas_Object *obj=elm_label_add(win);
 evas_object_size_hint_weight_set(obj,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
 evas_object_size_hint_align_set(obj,EVAS_HINT_FILL,EVAS_HINT_FILL);
 elm_box_pack_end(parent,obj);
 evas_object_show(obj);
 return obj;
}
static void window_close(void *data,Evas_Object *object,void *event){
 (void)data;(void)object;(void)event;
 (void)nx_tizen_film_dispatch(&ui.controller,NX_TIZEN_FILM_CANCEL);
 elm_exit();
}
int main(int argc,char **argv){
 if(elm_init(argc,argv)<=0)return 2;
 nx_film_menu saved;
 nx_film_menu_init(&saved);
 ui.settings_path=getenv("NX_FILM_CONFIG");
 if(ui.settings_path&&ui.settings_path[0])
  (void)nx_film_menu_load(&saved,ui.settings_path);
 else ui.settings_path=NULL;
 nx_tizen_film_controller_init(&ui.controller,saved.selected_id,
                                ui.settings_path?persist:NULL,
                                (void *)ui.settings_path);
 setup_input_mapping();
 (void)nx_tizen_film_dispatch(&ui.controller,NX_TIZEN_FILM_OPEN);
 ui.window=elm_win_add(NULL,"NX300M Film Simulator",ELM_WIN_BASIC);
 if(!ui.window){elm_shutdown();return 2;}
 elm_win_title_set(ui.window,"NX300M Film Simulator — Host/Tizen UI Study");
 elm_win_autodel_set(ui.window,EINA_TRUE);
 evas_object_smart_callback_add(ui.window,"delete,request",window_close,NULL);
 ui.root=elm_box_add(ui.window);
 elm_box_horizontal_set(ui.root,EINA_TRUE);
 evas_object_size_hint_weight_set(ui.root,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
 evas_object_size_hint_align_set(ui.root,EVAS_HINT_FILL,EVAS_HINT_FILL);
 elm_win_resize_object_add(ui.window,ui.root);
 evas_object_show(ui.root);
 ui.focus=elm_box_add(ui.window);
 evas_object_size_hint_weight_set(ui.focus,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
 evas_object_size_hint_align_set(ui.focus,EVAS_HINT_FILL,EVAS_HINT_FILL);
 elm_box_pack_end(ui.root,ui.focus);
 evas_object_show(ui.focus);
 ui.current=make_label(ui.window,ui.focus);
 ui.neighbors=make_label(ui.window,ui.focus);
 ui.status=make_label(ui.window,ui.focus);
 ui.sidebar=make_label(ui.window,ui.root);
 evas_object_event_callback_add(ui.window,EVAS_CALLBACK_KEY_DOWN,
                                on_key_down,NULL);
 evas_object_resize(ui.window,640,360);
 evas_object_focus_set(ui.window,EINA_TRUE);
 redraw(ui.settings_path?NULL:"PREVIEW ONLY: SET NX_FILM_CONFIG TO ENABLE SAVE");
 evas_object_show(ui.window);
 elm_run();
 elm_shutdown();
 return 0;
}
