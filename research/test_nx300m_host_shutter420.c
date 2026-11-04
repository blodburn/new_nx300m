#define _POSIX_C_SOURCE 200809L
/* Synthetic host shutter route regression. NEVER accesses a camera. */
#include "nx300m_host_shutter420.h"
#include "nx300m_preview_rgb.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum { W=34,H=22,YS=W+6,CS=W+8 };
static uint8_t y_plane[YS*H],c_plane[CS*(H/2)];
static const uint8_t raw_data[]={
  'S','Y','N','T','H','E','T','I','C',0,1,2,3,4,5
};
static const uint8_t app1[]={
  'E','x','i','f',0,0,'I','I',42,0,8,0,0,0,0,0,0,0,0,0
};
typedef struct {
 unsigned raw_calls, original_calls;
 int raw_failure, original_failure;
} calls;
static int raw_save(const void *p,size_t n,void *user){
 calls *c=user;
 assert(n==sizeof(raw_data)&&memcmp(p,raw_data,n)==0);
 c->raw_calls++;
 return c->raw_failure?-1:0;
}
static int original_save(void *user){
 calls *c=user;
 c->original_calls++;
 return c->original_failure?-1:0;
}
static void setup_planes(void){
 memset(y_plane,0xa5,sizeof(y_plane));
 memset(c_plane,0x5a,sizeof(c_plane));
 for(unsigned row=0;row<H;row++)
  for(unsigned x=0;x<W;x++)
   y_plane[(size_t)row*YS+x]=(uint8_t)(11u+x*7u+row*13u);
 for(unsigned row=0;row<H/2;row++)
  for(unsigned x=0;x<W;x++)
   c_plane[(size_t)row*CS+x]=(uint8_t)(31u+x*23u+row*19u);
}
static nx_rgb12 lut2[8];
static void setup_lut(void){
 for(unsigned b=0;b<2;b++)
  for(unsigned g=0;g<2;g++)
   for(unsigned r=0;r<2;r++)
    lut2[4*b+2*g+r]=(nx_rgb12){
      (uint16_t)(r?3900:0),(uint16_t)(g?3850:0),
      (uint16_t)(b?3800:0),0
    };
}
static nx_film_owned420_hypothesis_job input_job(
    const nx_preview_processor *p){
 nx_film_owned420_hypothesis_job job={0};
 job.copy_declaration=NX_FILM_420_COPY_DECLARATION;
 job.hypothesis=NX_FILM_BT601_FULL_CBCR_HYPOTHESIS;
 job.y=y_plane;job.y_stride=YS;job.y_bytes=sizeof(y_plane);
 job.chroma=c_plane;job.chroma_stride=CS;
 job.chroma_bytes=sizeof(c_plane);
 job.width=W;job.height=H;
 job.lut=lut2;job.lut_nodes=8u;job.grid=2u;
 job.decode_srgb=p->decode_srgb;job.decode_entries=256u;
 job.encode_srgb=p->encode_srgb;job.encode_entries=4096u;
 return job;
}
static int exists(const char *path){return access(path,F_OK)==0;}
static void is_jpeg(const char *path){
 FILE *f=fopen(path,"rb");assert(f);
 assert(fgetc(f)==0xff&&fgetc(f)==0xd8);
 assert(fseek(f,-2,SEEK_END)==0);
 assert(fgetc(f)==0xff&&fgetc(f)==0xd9);
 assert(fclose(f)==0);
}
static nx_host_shutter420_request base_req(calls *ctx){
 nx_host_shutter420_request r={0};
 r.mode=NX_SAVE_JPEG_ONLY;
 r.opaque_raw=raw_data;r.raw_bytes=sizeof(raw_data);
 r.write_raw=raw_save;r.write_original_jpeg=original_save;
 r.user=ctx;
 return r;
}
static void check_original_and_raw(void){
 calls ctx={0};
 nx_tizen_film_controller ctrl;
 nx_tizen_film_controller_init(&ctrl,0u,NULL,NULL);
 nx_host_shutter420_request r=base_req(&ctx);
 r.film_controller=&ctrl;
 nx_shutter_result result;
 assert(nx_host_shutter420_save_committed(&r,&result)==0);
 assert(result.selected_film_id==0u&&result.jpeg_saved==1u);
 assert(result.applied_film==0u&&result.raw_saved==0u);
 assert(ctx.original_calls==1u&&ctx.raw_calls==0u);
 r.mode=NX_SAVE_RAW_AND_JPEG;
 assert(nx_host_shutter420_save_committed(&r,&result)==0);
 assert(result.raw_saved==1u&&result.jpeg_saved==1u);
 assert(ctx.original_calls==2u&&ctx.raw_calls==1u);
 r.mode=NX_SAVE_RAW_ONLY;
 r.film_controller=NULL;
 r.write_original_jpeg=NULL;
 assert(nx_host_shutter420_save_committed(&r,&result)==0);
 assert(result.raw_saved==1u&&result.jpeg_saved==0u);
 assert(ctx.original_calls==2u&&ctx.raw_calls==2u);
 ctx.original_failure=1;
 r.mode=NX_SAVE_RAW_AND_JPEG;
 r.film_controller=&ctrl;
 r.write_original_jpeg=original_save;
 assert(nx_host_shutter420_save_committed(&r,&result)==-1);
 assert(result.raw_saved==1u&&result.jpeg_saved==0u);
 ctx.raw_failure=1;
 assert(nx_host_shutter420_save_committed(&r,&result)==-1);
 assert(result.raw_saved==0u&&result.jpeg_saved==0u);
 assert(ctx.original_calls==3u&&ctx.raw_calls==4u);
 puts("PASS: Original untouched, RAW_ONLY bypass, RAW+JPEG partial result");
}
static void check_film(const char *module){
 setup_planes();setup_lut();
 nx_preview_processor gamma;
 assert(nx_preview_init(&gamma)==0);
 nx_film_owned420_hypothesis_job job=input_job(&gamma);
 const uint8_t y_copy[sizeof(y_plane)]={0}; /* checked below via snapshots */
 (void)y_copy;
 uint8_t before_y[sizeof(y_plane)],before_c[sizeof(c_plane)];
 nx_rgb12 before_lut[8];
 memcpy(before_y,y_plane,sizeof(y_plane));
 memcpy(before_c,c_plane,sizeof(c_plane));
 memcpy(before_lut,lut2,sizeof(lut2));

 nx_tizen_film_controller ctrl;
 nx_tizen_film_controller_init(&ctrl,100u,NULL,NULL);
 assert(nx_tizen_film_dispatch(&ctrl,NX_TIZEN_FILM_OPEN)
        ==NX_TIZEN_FILM_CHANGED);
 assert(nx_tizen_film_dispatch(&ctrl,NX_TIZEN_FILM_ROTATE_CW)
        ==NX_TIZEN_FILM_CHANGED);
 nx_tizen_film_view view;
 assert(nx_tizen_film_view_state(&ctrl,&view)==0);
 assert(view.open&&view.dirty&&view.preview_id==101u);
 assert(view.committed_id==100u);

 char first[160],both[160],guard[160];
 assert(snprintf(first,sizeof(first),"outputs/committed_film_%ld.jpg",
                 (long)getpid())>0);
 assert(snprintf(both,sizeof(both),"outputs/committed_raw_film_%ld.jpg",
                 (long)getpid())>0);
 assert(snprintf(guard,sizeof(guard),"outputs/committed_guard_%ld.jpg",
                 (long)getpid())>0);
 assert(!exists(first)&&!exists(both)&&!exists(guard));
 calls ctx={0};
 nx_host_shutter420_request req=base_req(&ctx);
 req.film_controller=&ctrl;
 req.lut_preset_id=100u;
 req.copied_film_job=&job;
 req.freestanding_module_path=module;
 req.new_film_jpeg_path=first;
 req.original_exif_app1=app1;
 req.exif_bytes=sizeof(app1);
 nx_shutter_result result;
 assert(nx_host_shutter420_save_committed(&req,&result)==0);
 assert(result.selected_film_id==100u);
 assert(result.jpeg_saved==1u&&result.raw_saved==0u);
 assert(result.applied_film==1u&&result.original_fallback==0u);
 assert(ctx.raw_calls==0u&&ctx.original_calls==0u);
 is_jpeg(first);

 /* An unconfirmed preview MUST NOT apply its LUT to the shutter. */
 req.lut_preset_id=101u;req.new_film_jpeg_path=guard;
 req.mode=NX_SAVE_RAW_AND_JPEG;
 assert(nx_host_shutter420_save_committed(&req,&result)==-1);
 assert(!exists(guard)&&ctx.raw_calls==0u);
 assert(result.raw_saved==0u&&result.jpeg_saved==0u);
 req.lut_preset_id=100u;
 req.new_film_jpeg_path=both;
 assert(nx_host_shutter420_save_committed(&req,&result)==0);
 assert(result.raw_saved==1u&&result.jpeg_saved==1u);
 assert(ctx.raw_calls==1u&&ctx.original_calls==0u);
 is_jpeg(both);

 /* No overwrite; RAW saved first may remain on JPEG failure. */
 assert(nx_host_shutter420_save_committed(&req,&result)==-1);
 assert(result.raw_saved==1u&&result.jpeg_saved==0u);
 assert(ctx.raw_calls==2u);
 is_jpeg(both);

 /* Bad copied Y/C metadata fails closed without publishing any file. */
 req.mode=NX_SAVE_JPEG_ONLY;
 req.new_film_jpeg_path=guard;
 nx_film_owned420_hypothesis_job bad=job;
 bad.y_bytes=YS;
 req.copied_film_job=&bad;
 assert(nx_host_shutter420_save_committed(&req,&result)==-1);
 assert(!exists(guard));
 assert(memcmp(y_plane,before_y,sizeof(y_plane))==0);
 assert(memcmp(c_plane,before_c,sizeof(c_plane))==0);
 assert(memcmp(lut2,before_lut,sizeof(lut2))==0);

 assert(nx_tizen_film_dispatch(&ctrl,NX_TIZEN_FILM_CANCEL)
        ==NX_TIZEN_FILM_CHANGED);
 assert(ctrl.committed_id==100u);
 assert(unlink(first)==0&&unlink(both)==0);
 puts("PASS: committed Film 100, preview 101 ignored, single JPEG, "
      "RAW+JPEG, no-overwrite, immutable planes and LUT");
}
int main(int argc,char **argv){
 if(argc!=2||!argv[1])return 2;
 check_original_and_raw();
 check_film(argv[1]);
 puts("PASS NX300M host-only committed film-to-shutter route; "
      "NO firmware / DMA / native JPEG integration");
 return 0;
}
