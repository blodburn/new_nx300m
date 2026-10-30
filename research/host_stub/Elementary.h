#ifndef NX300M_EFL_TEST_STUB_ELEMENTARY_H
#define NX300M_EFL_TEST_STUB_ELEMENTARY_H
/* THIS IS AN OFFLINE SYNTAX-ONLY HEADER.
 * Never include it when linking an actual Tizen/ARM executable.
 * Real platform build must supply verified Samsung/Tizen EFL sysroot. */
typedef struct _Evas_Object Evas_Object;
typedef struct _Evas Evas;
typedef struct {const char *keyname;} Evas_Event_Key_Down;
typedef void (*Evas_Smart_Cb)(void*,Evas_Object*,void*);
typedef void (*Evas_Object_Event_Cb)(void*,Evas*,Evas_Object*,void*);
enum {EINA_TRUE=1,EVAS_CALLBACK_KEY_DOWN=1};
#define EVAS_HINT_EXPAND 1.0
#define EVAS_HINT_FILL -1.0
enum {ELM_WIN_BASIC=0};
int elm_init(int argc,char **argv);
void elm_shutdown(void);
void elm_run(void);
void elm_exit(void);
Evas_Object *elm_win_add(Evas_Object *parent,const char *name,int type);
void elm_win_title_set(Evas_Object *win,const char *title);
void elm_win_autodel_set(Evas_Object *win,int on);
void elm_win_resize_object_add(Evas_Object *win,Evas_Object *obj);
Evas_Object *elm_box_add(Evas_Object *parent);
void elm_box_horizontal_set(Evas_Object *box,int horizontal);
void elm_box_pack_end(Evas_Object *box,Evas_Object *subobject);
Evas_Object *elm_label_add(Evas_Object *parent);
void elm_object_text_set(Evas_Object *obj,const char *markup);
void evas_object_size_hint_weight_set(Evas_Object *obj,double x,double y);
void evas_object_size_hint_align_set(Evas_Object *obj,double x,double y);
void evas_object_smart_callback_add(Evas_Object *obj,const char *event,Evas_Smart_Cb fn,void *user);
void evas_object_event_callback_add(Evas_Object *obj,int type,Evas_Object_Event_Cb cb,void *user);
void evas_object_resize(Evas_Object *obj,int width,int height);
void evas_object_focus_set(Evas_Object *obj,int focused);
void evas_object_show(Evas_Object *obj);
#endif
