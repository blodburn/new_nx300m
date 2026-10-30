#include "nx300m_shutter_jpeg_bridge.h"
#include "nx300m_film_menu.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum { W=64,H=48,STRIDE=W*3+4,FRAME_BYTES=STRIDE*H };
static uint8_t rgb[FRAME_BYTES],preserved[FRAME_BYTES],raw[256];
typedef struct {
 unsigned jpeg_calls,raw_calls;
 unsigned char saved_rgb[FRAME_BYTES];
 unsigned char saved_raw[256];
 unsigned success_order[2],step;
 int fail_jpeg,fail_raw;
} mock;
static int on_jpeg(const unsigned char *frame,size_t stride,
                   unsigned width,unsigned height,void *opaque){
 mock *m=opaque;
 assert(frame&&stride==STRIDE&&width==W&&height==H);
 m->jpeg_calls++;
 if(m->step<2)m->success_order[m->step++]=2;
 memcpy(m->saved_rgb,frame,FRAME_BYTES);
 return m->fail_jpeg?-1:0;
}
static int on_raw(const void *data,size_t n,void *opaque){
 mock *m=opaque;
 assert(data==raw && n==sizeof(raw));
 m->raw_calls++;
 if(m->step<2)m->success_order[m->step++]=1;
 memcpy(m->saved_raw,data,n);
 return m->fail_raw?-1:0;
}
static void setup(void){
 for(unsigned y=0;y<H;y++){
  for(unsigned x=0;x<W;x++){
   unsigned offset=y*STRIDE+3*x;
   rgb[offset+0]=(uint8_t)(30+(x*3+y)%180);
   rgb[offset+1]=(uint8_t)(20+(x+2*y)%180);
   rgb[offset+2]=(uint8_t)(25+(2*x+3*y)%200);
  }
  memset(rgb+y*STRIDE+W*3,0xcc,STRIDE-W*3);
 }
 memcpy(preserved,rgb,sizeof(rgb));
 for(unsigned i=0;i<sizeof(raw);i++)raw[i]=(uint8_t)(i*7u);
}
static nx_shutter_request req(mock *m,nx_save_mode mode,const char *path){
 nx_shutter_request q={0};
 q.mode=mode;q.saved_film_setting=path;q.decoded_rgb=rgb;
 q.rgb_bytes=FRAME_BYTES;q.rgb_stride=STRIDE;q.width=W;q.height=H;
 q.opaque_raw=raw;q.raw_bytes=sizeof(raw);
 q.write_jpeg=on_jpeg;q.write_raw=on_raw;q.user=m;
 return q;
}
static void untouched(void){assert(!memcmp(preserved,rgb,sizeof(rgb)));}
static void test_one_jpeg(unsigned film,unsigned expect_effect){
 nx_film_menu m;nx_film_menu_init(&m);m.selected_id=film;
 assert(nx_film_menu_store(&m,"outputs/test_selected_for_shutter.cfg")==0);
 mock calls={0};nx_shutter_result result={0};
 nx_shutter_request q=req(&calls,NX_SAVE_JPEG_ONLY,
                        "outputs/test_selected_for_shutter.cfg");
 assert(nx_shutter_save_selected(&q,&result)==0);
 assert(calls.jpeg_calls==1&&calls.raw_calls==0);
 assert(result.jpeg_saved==1&&result.raw_saved==0);
 assert(result.selected_film_id==film);
 assert(result.applied_film==expect_effect);
 if(!expect_effect)assert(!memcmp(calls.saved_rgb,rgb,FRAME_BYTES));
 else assert(memcmp(calls.saved_rgb,rgb,FRAME_BYTES)!=0);
 untouched();
}
int main(void){
 setup();
 assert(nx_film_count()==13);
 for(unsigned i=0;i<nx_film_count();i++){
   const nx_film_preset *preset=nx_film_by_index(i);
   assert(preset);
   test_one_jpeg(preset->id,preset->id!=0);
 }
 mock m={0};nx_shutter_result out={0};
 nx_shutter_request q=req(&m,NX_SAVE_JPEG_ONLY,"outputs/missing_config_jpeg.cfg");
 assert(nx_shutter_save_selected(&q,&out)==0);
 assert(m.jpeg_calls==1&&m.raw_calls==0&&out.selected_film_id==0);
 assert(out.original_fallback==1&&out.applied_film==0);
 assert(!memcmp(m.saved_rgb,rgb,FRAME_BYTES));untouched();
 memset(&m,0,sizeof(m));memset(&out,0,sizeof(out));
 q=req(&m,NX_SAVE_RAW_AND_JPEG,"outputs/test_selected_for_shutter.cfg");
 assert(nx_shutter_save_selected(&q,&out)==0);
 assert(m.raw_calls==1&&m.jpeg_calls==1);
 assert(m.success_order[0]==1&&m.success_order[1]==2);
 assert(out.jpeg_saved==1&&out.raw_saved==1);
 assert(!memcmp(m.saved_raw,raw,sizeof(raw)));untouched();
 memset(&m,0,sizeof(m));memset(&out,0,sizeof(out));
 q=req(&m,NX_SAVE_RAW_ONLY,NULL);
 q.decoded_rgb=NULL;q.rgb_bytes=0;q.write_jpeg=NULL;
 assert(nx_shutter_save_selected(&q,&out)==0);
 assert(m.raw_calls==1&&m.jpeg_calls==0);
 assert(out.raw_saved==1&&out.jpeg_saved==0);
 untouched();
 memset(&m,0,sizeof(m));m.fail_raw=1;
 q=req(&m,NX_SAVE_RAW_AND_JPEG,"outputs/test_selected_for_shutter.cfg");
 assert(nx_shutter_save_selected(&q,&out)==-1);
 assert(m.raw_calls==1&&m.jpeg_calls==0);
 assert(out.raw_saved==0&&out.jpeg_saved==0);
 untouched();
 memset(&m,0,sizeof(m));m.fail_jpeg=1;
 q=req(&m,NX_SAVE_JPEG_ONLY,"outputs/test_selected_for_shutter.cfg");
 assert(nx_shutter_save_selected(&q,&out)==-1);
 assert(m.jpeg_calls==1&&m.raw_calls==0&&out.jpeg_saved==0);untouched();
 memset(&m,0,sizeof(m));memset(&out,0,sizeof(out));
 q=req(&m,NX_SAVE_JPEG_ONLY,"outputs/test_selected_for_shutter.cfg");
 q.rgb_bytes=FRAME_BYTES-1;
 assert(nx_shutter_save_selected(&q,&out)==-1);
 assert(m.jpeg_calls==0&&m.raw_calls==0);untouched();
 q=req(&m,NX_SAVE_JPEG_ONLY,"outputs/test_selected_for_shutter.cfg");
 q.rgb_stride=3*W-1;
 assert(nx_shutter_save_selected(&q,&out)==-1);
 assert(m.jpeg_calls==0);untouched();
 q=req(&m,NX_SAVE_JPEG_ONLY,"outputs/test_selected_for_shutter.cfg");
 q.write_jpeg=NULL;
 assert(nx_shutter_save_selected(&q,&out)==-1);
 assert(m.jpeg_calls==0);untouched();
 q=req(&m,(nx_save_mode)9,"outputs/test_selected_for_shutter.cfg");
 assert(nx_shutter_save_selected(&q,&out)==-1);untouched();
 puts("PASS 13 fixed FILM LOOKS JPEG_ONLY exactly 1 JPEG no RAW; RAW_AND_JPEG 1 each, RAW_ONLY raw only, saved look, original and fallback, metadata validation and no input modification");
 return 0;
}
