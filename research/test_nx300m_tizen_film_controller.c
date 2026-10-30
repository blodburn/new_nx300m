#define _POSIX_C_SOURCE 200809L
#include "nx300m_tizen_film_controller.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
typedef struct {unsigned calls,id;int fail;} save_probe;
static int save_stub(void *user,unsigned id){
 save_probe *p=user;p->calls++;p->id=id;return p->fail?-1:0;
}
static void view_match(nx_tizen_film_controller *c,unsigned expected,
                       int opened,int dirty){
 nx_tizen_film_view v;
 assert(nx_tizen_film_view_state(c,&v)==0);
 assert(v.preview_id==expected&&v.open==opened&&v.dirty==dirty);
 assert(v.count==13);
 assert(v.preview_index<13);
 assert(v.preview_name&&v.preview_description);
 assert(v.preceding_name&&v.following_name);
}
static void test_all_13(void){
 for(size_t index=0;index<nx_film_count();index++){
  save_probe p={0,0,0};nx_tizen_film_controller c;
  const nx_film_preset *source=nx_film_by_index(index);
  const nx_film_preset *next=nx_film_by_index((index+1)%13);
  const nx_film_preset *prior=nx_film_by_index((index+12)%13);
  assert(source&&next&&prior);
  nx_tizen_film_controller_init(&c,source->id,save_stub,&p);
  view_match(&c,source->id,0,0);
  assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_ROTATE_CW)==0);
  assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_OPEN)==1);
  assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_OPEN)==0);
  assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_ROTATE_CW)==1);
  view_match(&c,next->id,1,1);
  assert(c.committed_id==source->id&&p.calls==0);
  assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CANCEL)==1);
  view_match(&c,source->id,0,0);
  assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_OPEN)==1);
  assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_ROTATE_CCW)==1);
  view_match(&c,prior->id,1,1);
  assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CONFIRM)==2);
  view_match(&c,prior->id,0,0);
  assert(c.committed_id==prior->id&&p.calls==1&&p.id==prior->id);
 }
}
static void test_persistence_failure(void){
 save_probe p={0,0,1};nx_tizen_film_controller c;
 nx_tizen_film_controller_init(&c,103,save_stub,&p);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_OPEN)==1);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_ROTATE_CW)==1);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CONFIRM)==-1);
 view_match(&c,104,1,1);
 assert(c.committed_id==103&&p.calls==1);
 p.fail=0;
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CONFIRM)==2);
 assert(c.committed_id==104&&p.calls==2);
}
static void test_invalid_and_no_saver(void){
 nx_tizen_film_controller c;
 nx_tizen_film_controller_init(&c,999,NULL,NULL);
 view_match(&c,0,0,0);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CONFIRM)==0);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_OPEN)==1);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CONFIRM)==0);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_OPEN)==1);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_ROTATE_CW)==1);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CONFIRM)==-1);
 view_match(&c,100,1,1);
 assert(nx_tizen_film_dispatch(&c,NX_TIZEN_FILM_CANCEL)==1);
 assert(nx_tizen_film_dispatch(&c,(enum nx_tizen_film_event)99)==-1);
 assert(nx_tizen_film_view_state(NULL,NULL)==-1);
 assert(nx_tizen_film_dispatch(NULL,NX_TIZEN_FILM_OPEN)==-1);
 nx_tizen_film_controller_init(&c,300,NULL,NULL);
 view_match(&c,200,0,0); /* legacy Leica ID normalization */
}
static void test_atomic_file(void){
 char dirname[]="/tmp/nx300m-filmsim-test-XXXXXX";
 assert(mkdtemp(dirname)!=NULL);
 char path[256],invalid[256],symlinkpath[256];
 int k=snprintf(path,sizeof(path),"%s/filmmode.cfg",dirname);
 assert(k>0&&(size_t)k<sizeof(path));
 k=snprintf(invalid,sizeof(invalid),"%s/nonexistent/out.cfg",dirname);
 assert(k>0&&(size_t)k<sizeof(invalid));
 k=snprintf(symlinkpath,sizeof(symlinkpath),"%s/symlink.cfg",dirname);
 assert(k>0&&(size_t)k<sizeof(symlinkpath));
 FILE *f=fopen(path,"wb");assert(f);
 assert(fputs("ORIGINAL_CONTENT",f)>=0&&fclose(f)==0);
 assert(nx_tizen_film_save_file(invalid,103)==-1);
 f=fopen(path,"rb");assert(f);
 char contents[100]={0};
 assert(fread(contents,1,16,f)==16&&fclose(f)==0);
 assert(memcmp(contents,"ORIGINAL_CONTENT",16)==0);
 assert(symlink(path,symlinkpath)==0);
 assert(nx_tizen_film_save_file(symlinkpath,103)==-1);
 assert(nx_tizen_film_save_file(path,999)==-1);
 assert(nx_tizen_film_save_file(NULL,101)==-1);
 assert(nx_tizen_film_save_file(path,103)==0);
 nx_film_menu menu;nx_film_menu_init(&menu);
 assert(nx_film_menu_load(&menu,path)==0&&menu.selected_id==103);
 assert(nx_tizen_film_save_file(path,204)==0);
 nx_film_menu_init(&menu);
 assert(nx_film_menu_load(&menu,path)==0&&menu.selected_id==204);
 assert(unlink(symlinkpath)==0);
 assert(unlink(path)==0);
 assert(rmdir(dirname)==0);
}
int main(void){
 assert(nx_film_count()==13);
 test_all_13();
 test_persistence_failure();
 test_invalid_and_no_saver();
 test_atomic_file();
 puts("PASS Tizen Film Controller: 13 dial wrap/cancel/confirm, preview is transient, failure does not change active preset, explicit atomic config save, legacy ID normalization, symlink refusal");
 return 0;
}
