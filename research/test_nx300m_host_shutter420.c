#define _POSIX_C_SOURCE 200809L
/* Synthetic host shutter route regression. NEVER accesses a camera. */
#include "nx300m_host_shutter420.h"
#include "nx300m_host_preview420.h"
#include "nx300m_preview_rgb.h"
#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum { W=34,H=22,YS=W+6,CS=W+8,PREVIEW_STRIDE=W*3+7 };
typedef int (*render_rows_fn)(const nx_film_owned420_hypothesis_job *,
                              unsigned,unsigned);
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
 int mutate_yc_on_raw;
} calls;
static int raw_save(const void *p,size_t n,void *user){
 calls *c=user;
 assert(n==sizeof(raw_data)&&memcmp(p,raw_data,n)==0);
 c->raw_calls++;
 /* Simulate a caller-managed capture buffer released or reused as soon
  * as the RAW writer callback starts. The JPEG must use a prior snapshot. */
 if(c->mutate_yc_on_raw){
  memset(y_plane,0,sizeof(y_plane));
  memset(c_plane,0,sizeof(c_plane));
 }
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
 /* Original bypasses preview math without opening a DSO or reading pixels. */
 nx_host_preview420_request original_preview={0};
 original_preview.controller=&ctrl;
 unsigned shown=777u;
 assert(nx_host_preview420_apply(&original_preview,&shown)==
        NX_HOST_PREVIEW420_BYPASSED);
 assert(shown==0u);
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
 /* Unconfirmed wheel choice is a real preview pixel transform.
  * Shutter selection is still committed Film 100. */
 uint8_t live_preview[H*PREVIEW_STRIDE],committed_preview[H*PREVIEW_STRIDE];
 memset(live_preview,0xcc,sizeof(live_preview));
 nx_host_preview420_request preview={0};
 preview.controller=&ctrl;
 preview.copied_input=&job;
 preview.freestanding_module_path=module;
 preview.output_rgb=live_preview;
 preview.output_bytes=sizeof(live_preview);
 preview.output_stride=PREVIEW_STRIDE;
 unsigned shown=999u;
 assert(nx_host_preview420_apply(&preview,&shown)==
        NX_HOST_PREVIEW420_APPLIED);
 assert(shown==101u);

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
 memset(committed_preview,0xcc,sizeof(committed_preview));
 preview.output_rgb=committed_preview;
 preview.output_bytes=sizeof(committed_preview);
 assert(nx_host_preview420_apply(&preview,&shown)==
        NX_HOST_PREVIEW420_APPLIED);
 assert(shown==100u);
 assert(memcmp(live_preview,committed_preview,
               sizeof(live_preview))!=0);
 assert(unlink(first)==0&&unlink(both)==0);
 puts("PASS: committed Film 100, preview 101 ignored, single JPEG, "
      "RAW+JPEG, no-overwrite, immutable planes and LUT");
}

/* For every real non-Original menu ID, prove JPEG bytes originate from the
 * factory-built fixed 18^3 LUT, not the arbitrary LUT pointer supplied by
 * the caller. This is an offline HOST geometry, never an NX300M device.
 */
static uint64_t jpg_fingerprint(const char *path){
 FILE *fp=fopen(path,"rb");assert(fp);
 uint64_t hash=UINT64_C(14695981039346656037);
 int value;unsigned total=0u;
 while((value=fgetc(fp))!=EOF){
  hash^=(uint8_t)value;
  hash*=UINT64_C(1099511628211);
  total++;
 }
 assert(!ferror(fp)&&fclose(fp)==0&&total>200u);
 return hash;
}
static void assert_same_jpeg_bytes(const char *a,const char *b){
 FILE *x=fopen(a,"rb"),*y=fopen(b,"rb");assert(x&&y);
 for(;;){
  const int ch=fgetc(x),other=fgetc(y);
  assert(ch==other);
  if(ch==EOF)break;
 }
 assert(!ferror(x)&&!ferror(y));
 assert(fclose(x)==0&&fclose(y)==0);
}
static void check_snapshot_before_raw(const char *module){
 setup_planes();setup_lut();
 nx_preview_processor gamma;
 assert(nx_preview_init(&gamma)==0);
 nx_film_owned420_hypothesis_job job=input_job(&gamma);
 job.lut=NULL;job.lut_nodes=0u;job.grid=0u;

 nx_tizen_film_controller ctrl;
 nx_tizen_film_controller_init(&ctrl,100u,NULL,NULL);
 calls ctx={0};
 nx_host_shutter420_request req=base_req(&ctx);
 req.film_controller=&ctrl;
 req.copied_film_job=&job;
 req.lut_preset_id=100u;
 req.freestanding_module_path=module;
 req.original_exif_app1=app1;
 req.exif_bytes=sizeof(app1);
 char baseline[160],altered[160],failed[160];
 assert(snprintf(baseline,sizeof(baseline),
     "outputs/preflight_baseline_%ld.jpg",(long)getpid())>0);
 assert(snprintf(altered,sizeof(altered),
     "outputs/preflight_mutated_%ld.jpg",(long)getpid())>0);
 assert(snprintf(failed,sizeof(failed),
     "outputs/preflight_reject_%ld.jpg",(long)getpid())>0);
 assert(!exists(baseline)&&!exists(altered)&&!exists(failed));
 nx_shutter_result result;
 req.mode=NX_SAVE_JPEG_ONLY;
 req.new_film_jpeg_path=baseline;
 assert(nx_host_shutter420_save_committed(&req,&result)==0);
 is_jpeg(baseline);

 /* RAW callback overwrites the source Y/C allocations in place. The
  * previously acquired film snapshot must still produce identical JPEG. */
 ctx.mutate_yc_on_raw=1;
 req.mode=NX_SAVE_RAW_AND_JPEG;
 req.new_film_jpeg_path=altered;
 assert(nx_host_shutter420_save_committed(&req,&result)==0);
 assert(ctx.raw_calls==1u&&ctx.original_calls==0u);
 assert(result.raw_saved==1u&&result.jpeg_saved==1u);
 assert_same_jpeg_bytes(baseline,altered);

 /* Invalid source input must be refused BEFORE the RAW callback fires. */
 setup_planes();
 ctx.mutate_yc_on_raw=0;
 nx_film_owned420_hypothesis_job bad=job;
 bad.y_bytes=YS;
 req.copied_film_job=&bad;
 req.new_film_jpeg_path=failed;
 assert(nx_host_shutter420_save_committed(&req,&result)==-1);
 assert(ctx.raw_calls==1u);
 assert(result.raw_saved==0u&&result.jpeg_saved==0u);
 assert(!exists(failed));

 /* Decoder table input is also validated before the RAW side effect. */
 uint16_t corrupt_decode[256];
 memcpy(corrupt_decode,gamma.decode_srgb,sizeof(corrupt_decode));
 corrupt_decode[40]=4096u;
 bad=job;
 bad.decode_srgb=corrupt_decode;
 req.copied_film_job=&bad;
 assert(nx_host_shutter420_save_committed(&req,&result)==-1);
 assert(ctx.raw_calls==1u);
 assert(!exists(failed));

 assert(unlink(baseline)==0&&unlink(altered)==0);
 puts("PASS shutter preflight before RAW: no partial RAW on invalid Y/C; "
      "source reuse during RAW does not change JPEG");
}
static void check_all_committed_looks(const char *module){
 setup_planes();setup_lut();
 nx_preview_processor gamma;
 assert(nx_preview_init(&gamma)==0);
 nx_film_owned420_hypothesis_job input=input_job(&gamma);
 /* No caller LUT is provided: the shutter MUST build the film transform
  * from the selected menu entry, not a fallback preset table. */
 input.lut=NULL;
 input.lut_nodes=0u;
 input.grid=0u;
 uint8_t source_y[sizeof(y_plane)],source_c[sizeof(c_plane)];
 nx_rgb12 source_lut[sizeof(lut2)/sizeof(lut2[0])];
 memcpy(source_y,y_plane,sizeof(y_plane));
 memcpy(source_c,c_plane,sizeof(c_plane));
 memcpy(source_lut,lut2,sizeof(lut2));
 unsigned ids[13]={0};
 uint64_t hashes[13]={0};
 unsigned count=0u;
 nx_rgb12 *reference_lut=malloc((size_t)NX_LUT_COUNT*sizeof(*reference_lut));
 assert(reference_lut);
 void *kernel=dlopen(module,RTLD_NOW|RTLD_LOCAL);
 assert(kernel);
 render_rows_fn render=(render_rows_fn)
    dlsym(kernel,"nx_film_core_render_owned420_rows_hypothesis");
 assert(render);
 for(size_t index=0;index<nx_film_count();index++){
  const nx_film_preset *p=nx_film_by_index(index);
  assert(p);
  if(p->id==0u)continue;
  assert(count<13u);
  ids[count]=p->id;

  nx_tizen_film_controller ctrl;
  nx_tizen_film_controller_init(&ctrl,p->id,NULL,NULL);
  calls ctx={0};
  nx_host_shutter420_request req=base_req(&ctx);
  req.film_controller=&ctrl;
  req.lut_preset_id=p->id;
  req.copied_film_job=&input;
  req.freestanding_module_path=module;
  req.original_exif_app1=app1;
  req.exif_bytes=sizeof(app1);
  char output[160],oracle[160];
  assert(snprintf(output,sizeof(output),
       "outputs/selected_%ld_%u.jpg",(long)getpid(),p->id)>0);
  assert(snprintf(oracle,sizeof(oracle),
       "outputs/selected_oracle_%ld_%u.jpg",(long)getpid(),p->id)>0);
  assert(!exists(output)&&!exists(oracle));
  req.new_film_jpeg_path=output;

  nx_shutter_result result;
  assert(nx_host_shutter420_save_committed(&req,&result)==0);
  assert(result.applied_film==1u&&result.jpeg_saved==1u);
  assert(result.selected_film_id==p->id);
  assert(ctx.raw_calls==0u&&ctx.original_calls==0u);
  is_jpeg(output);

  nx_film_menu expected_menu;
  nx_film_menu_init(&expected_menu);
  expected_menu.selected_id=p->id;
  assert(nx_film_lut_for_menu(&expected_menu,reference_lut)==0);
  nx_film_owned420_hypothesis_job oracle_job=input;
  oracle_job.lut=reference_lut;
  oracle_job.lut_nodes=NX_LUT_COUNT;
  oracle_job.grid=NX_LUT_GRID;
  /* The HOST preview is computed from the same LUT18 as the JPEG
   * pre-encode RGB row path, with no caller-provided LUT. */
  uint8_t shown_rgb[H*PREVIEW_STRIDE],expected_rgb[H*W*3];
  memset(shown_rgb,0xcc,sizeof(shown_rgb));
  nx_host_preview420_request preview={0};
  preview.controller=&ctrl;
  preview.copied_input=&input;
  preview.freestanding_module_path=module;
  preview.output_rgb=shown_rgb;
  preview.output_bytes=sizeof(shown_rgb);
  preview.output_stride=PREVIEW_STRIDE;
  unsigned shown=999u;
  assert(nx_host_preview420_apply(&preview,&shown)==
         NX_HOST_PREVIEW420_APPLIED&&shown==p->id);
  oracle_job.rgb=expected_rgb;
  oracle_job.rgb_bytes=sizeof(expected_rgb);
  oracle_job.rgb_stride=W*3u;
  assert(render(&oracle_job,0u,H)==0);
  for(unsigned row=0;row<H;row++){
   assert(memcmp(shown_rgb+(size_t)row*PREVIEW_STRIDE,
                 expected_rgb+(size_t)row*W*3u,W*3u)==0);
   for(unsigned x=W*3u;x<PREVIEW_STRIDE;x++)
    assert(shown_rgb[(size_t)row*PREVIEW_STRIDE+x]==0xccu);
  }
  uint8_t guard[sizeof(shown_rgb)];
  memcpy(guard,shown_rgb,sizeof(guard));
  preview.output_bytes=W*3u-1u;
  assert(nx_host_preview420_apply(&preview,&shown)==
         NX_HOST_PREVIEW420_INVALID);
  assert(memcmp(shown_rgb,guard,sizeof(guard))==0);
  assert(nx_host_freestanding420_jpeg_copy(
     module,&oracle_job,0,oracle,app1,sizeof(app1))==0);
  assert_same_jpeg_bytes(output,oracle);
  hashes[count]=jpg_fingerprint(output);
  assert(memcmp(y_plane,source_y,sizeof(y_plane))==0);
  assert(memcmp(c_plane,source_c,sizeof(c_plane))==0);
  assert(memcmp(lut2,source_lut,sizeof(lut2))==0);
  assert(unlink(output)==0&&unlink(oracle)==0);
  count++;
 }
 assert(count==nx_film_count()-1u);
 for(unsigned i=0;i<count;i++)
  for(unsigned j=i+1u;j<count;j++){
   /* The 12 fixed looks must result in distinguishable JPEG bitstreams
    * when the source frame and EXIF are held constant. */
   if(hashes[i]==hashes[j]){
    fprintf(stderr,"IDENTICAL LOOKS: %u / %u\n",ids[i],ids[j]);
    assert(hashes[i]!=hashes[j]);
   }
  }
 assert(dlclose(kernel)==0);
 free(reference_lut);
 printf("PASS host preview420 pixel-to-JPEG source parity for %u looks\n",count);
 printf("PASS committed LUT18-to-JPEG: %u distinct menu looks, "
        "exact factory LUT parity, NO caller LUT required\n",count);
}
int main(int argc,char **argv){
 if(argc!=2||!argv[1])return 2;
 check_original_and_raw();
 check_film(argv[1]);
 check_snapshot_before_raw(argv[1]);
 check_all_committed_looks(argv[1]);
 puts("PASS NX300M host-only committed film-to-shutter route; "
      "NO firmware / DMA / native JPEG integration");
 return 0;
}
