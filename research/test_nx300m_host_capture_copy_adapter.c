#define _POSIX_C_SOURCE 200809L
#include "nx300m_host_capture_copy_adapter.h"
#include "nx300m_film_menu.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum {W=96,H=40,STRIDE=W*3+7,SPAN=STRIDE*H};
static uint8_t source[SPAN],original[SPAN],target[SPAN],target_before[SPAN];
static char path[160];

static void reset_target(void){
 memset(target,0x9a,sizeof(target));
 memcpy(target_before,target,sizeof(target));
}
static nx_host_copy_job make_job(void){
 nx_host_copy_job j={path,NX_PW_SOURCE_HOST_COPIED_FRAME,
                   NX_PW_CAPTURE_JPEG_ONLY,1,
                   source,SPAN,target,SPAN,STRIDE,W,H};
 return j;
}
static void select_preset(unsigned id){
 nx_film_menu m;
 nx_film_menu_init(&m);
 m.selected_id=id;
 assert(nx_film_menu_store(&m,path)==0);
}
static void unchanged(void){
 assert(memcmp(source,original,sizeof(source))==0);
 assert(memcmp(target,target_before,sizeof(target))==0);
}
static void test_all_13(void){
 for(size_t i=0;i<nx_film_count();i++){
  const nx_film_preset *p=nx_film_by_index(i);
  assert(p);
  select_preset(p->id);
  nx_host_copy_job j=make_job();
  reset_target();
  const int result=nx_host_capture_apply_copy(&j);
  if(p->id==0){
   assert(result==NX_HOST_COPY_BYPASSED);
   unchanged();
  }else{
   assert(result==NX_HOST_COPY_APPLIED);
   assert(memcmp(target,target_before,sizeof(target))!=0);
   assert(memcmp(source,original,sizeof(source))==0);
   /* Alignment/padding bytes are not part of image pixels. */
   for(unsigned y=0;y<H;y++)
    for(unsigned col=W*3;col<STRIDE;col++)
     assert(target[(size_t)y*STRIDE+col]==source[(size_t)y*STRIDE+col]);
  }
 }
}
static void test_reject_and_no_partial_write(void){
 select_preset(201);
 nx_host_copy_job j=make_job();
 reset_target();
 j.source=NX_PW_SOURCE_CAMERA_DEVICE;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.capture_mode=NX_PW_CAPTURE_RAW_ONLY;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.rgb888_validated=0;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.src_bytes=SPAN-1;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.dst_bytes=SPAN-1;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.stride=W*3-1;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.stride=(size_t)-1;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.width=0;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.height=0;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.width=20000;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.height=20000;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.width=16384;j.height=16384;
 j.stride=16384u*3u;
 j.src_bytes=j.stride*(size_t)j.height;
 j.dst_bytes=j.src_bytes;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.dst=source;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.src=NULL;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.dst=NULL;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 j=make_job();j.config_path=NULL;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);unchanged();
 assert(nx_host_capture_apply_copy(NULL)==NX_HOST_COPY_INVALID);unchanged();
}
static void test_partial_overlap(void){
 uint8_t *alias=malloc(SPAN+16u);
 assert(alias);
 for(size_t i=0;i<SPAN+16u;i++)alias[i]=(uint8_t)(i*13+71);
 uint8_t *snapshot=malloc(SPAN+16u);
 assert(snapshot);memcpy(snapshot,alias,SPAN+16u);
 nx_host_copy_job j=make_job();
 j.src=alias;j.dst=alias+1;
 reset_target();
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);
 assert(memcmp(alias,snapshot,SPAN+16u)==0);
 unchanged();
 j.src=alias+1;j.dst=alias;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_INVALID);
 assert(memcmp(alias,snapshot,SPAN+16u)==0);
 unchanged();
 free(snapshot);free(alias);
}
static void test_bypass(void){
 select_preset(0);
 reset_target();
 nx_host_copy_job j=make_job();
 j.source=NX_PW_SOURCE_CAMERA_DEVICE;
 j.src=NULL;j.dst=NULL;j.src_bytes=0;j.dst_bytes=0;
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_BYPASSED);
 unchanged();
 assert(unlink(path)==0);
 j=make_job();
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_BYPASSED);
 unchanged();
 FILE *f=fopen(path,"wb");assert(f);
 assert(fputs("damaged config\n",f)>=0);
 assert(fclose(f)==0);
 assert(nx_host_capture_apply_copy(&j)==NX_HOST_COPY_BYPASSED);
 unchanged();
}
int main(void){
 char dir[]="/tmp/nx300m-copy-adapter-XXXXXX";
 assert(mkdtemp(dir));
 int n=snprintf(path,sizeof(path),"%s/look.cfg",dir);
 assert(n>0&&(size_t)n<sizeof(path));
 for(size_t i=0;i<sizeof(source);i++)source[i]=(uint8_t)((i*73u+19u)&255u);
 memcpy(original,source,sizeof(source));
 test_all_13();
 test_reject_and_no_partial_write();
 test_partial_overlap();
 test_bypass();
 assert(unlink(path)==0);
 assert(rmdir(dir)==0);
 puts("PASS host-copy bridge: 13 looks; source untouched; output atomic on success; bounds/overlap/destination refusal; camera/RAW blocked; missing config original bypass; pixel padding unchanged");
 return 0;
}
