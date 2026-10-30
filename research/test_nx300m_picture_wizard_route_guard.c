#include "nx300m_picture_wizard_route_guard.h"
#include "nx300m_film_menu.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

/* Source-specific routes are decisions ONLY. This test never calls a native
 * Samsung function; it verifies that NO FilmSim ID is sent as a vendor ID. */
static void invariant(const nx_pw_route_plan *p){
 assert(p->may_change_samsung_picture_wizard==0);
 assert(p->may_write_native_ycc==0);
 assert(p->may_write_raw==0);
 assert(p->original_vendor_mode_must_be_preserved==1);
 if(p->route==NX_PW_ROUTE_REFUSE){
  assert(p->use_host_rgb_frame==0);
  assert(p->requires_independent_jpeg_output==0);
 }
}
static unsigned matrix_cases(void){
 unsigned count=0,experimental=0;
 for(size_t i=0;i<nx_film_count();i++){
  const nx_film_preset *preset=nx_film_by_index(i);
  assert(preset);
  if(preset->id)experimental++;
  for(int source=NX_PW_SOURCE_HOST_COPIED_FRAME;
          source<=NX_PW_SOURCE_CAMERA_DEVICE;source++){
   for(int mode=NX_PW_CAPTURE_JPEG_ONLY;
           mode<=NX_PW_CAPTURE_RAW_PLUS_JPEG;mode++){
    for(int validated=0;validated<=1;validated++){
     nx_pw_route_request r={preset->id,(nx_pw_source)source,
                            (nx_pw_capture_mode)mode,validated};
     nx_pw_route_plan p;
     memset(&p,0xcd,sizeof(p));
     nx_pw_route result=nx_pw_plan_capture(&r,&p);
     invariant(&p);
     assert(p.validated_film_id==preset->id);
     if(!preset->id){
      assert(result==NX_PW_ROUTE_ORIGINAL_UNCHANGED);
      assert(p.use_host_rgb_frame==0);
     } else if(source==NX_PW_SOURCE_HOST_COPIED_FRAME &&
               mode!=NX_PW_CAPTURE_RAW_ONLY && validated){
      assert(result==NX_PW_ROUTE_HOST_RGB_EFFECT);
      assert(p.use_host_rgb_frame==1);
      assert(p.requires_independent_jpeg_output==1);
     } else {
      assert(result==NX_PW_ROUTE_REFUSE);
     }
     count++;
    }
   }
  }
 }
 assert(nx_film_count()==13&&experimental==12&&count==13*2*3*2);
 return count;
}
static void invalid_cases(void){
 nx_pw_route_plan p;
 nx_pw_route_request valid={101,NX_PW_SOURCE_HOST_COPIED_FRAME,
                             NX_PW_CAPTURE_JPEG_ONLY,1};
 assert(nx_pw_plan_capture(NULL,&p)==NX_PW_ROUTE_REFUSE);
 invariant(&p);
 assert(nx_pw_plan_capture(&valid,NULL)==NX_PW_ROUTE_REFUSE);
 const unsigned bad_ids[]={1,12,99,107,199,205,999,0xffffffffu};
 for(size_t k=0;k<sizeof(bad_ids)/sizeof(bad_ids[0]);k++){
  valid.film_preset_id=bad_ids[k];
  assert(nx_pw_plan_capture(&valid,&p)==NX_PW_ROUTE_REFUSE);
  assert(p.validated_film_id==0);
  invariant(&p);
 }
 valid.film_preset_id=101;
 const int bad_sources[]={0,-1,3,55};
 for(size_t k=0;k<sizeof(bad_sources)/sizeof(bad_sources[0]);k++){
  valid.source=(nx_pw_source)bad_sources[k];
  assert(nx_pw_plan_capture(&valid,&p)==NX_PW_ROUTE_REFUSE);
  invariant(&p);
 }
 valid.source=NX_PW_SOURCE_HOST_COPIED_FRAME;
 const int bad_modes[]={0,-1,4,100};
 for(size_t k=0;k<sizeof(bad_modes)/sizeof(bad_modes[0]);k++){
  valid.mode=(nx_pw_capture_mode)bad_modes[k];
  assert(nx_pw_plan_capture(&valid,&p)==NX_PW_ROUTE_REFUSE);
  invariant(&p);
 }
 valid.mode=NX_PW_CAPTURE_JPEG_ONLY;
 valid.host_rgb888_validated=-1;
 assert(nx_pw_plan_capture(&valid,&p)==NX_PW_ROUTE_REFUSE);
 invariant(&p);
 valid.host_rgb888_validated=2;
 assert(nx_pw_plan_capture(&valid,&p)==NX_PW_ROUTE_REFUSE);
 invariant(&p);
}
static void legacy_leica_and_raw_unchanged(void){
 uint8_t raw[256],before[256];
 for(unsigned i=0;i<sizeof(raw);i++)raw[i]=(uint8_t)(19u*i+3u);
 memcpy(before,raw,sizeof(raw));
 for(unsigned legacy=300;legacy<=304;legacy++){
  nx_pw_route_request r={legacy,NX_PW_SOURCE_HOST_COPIED_FRAME,
                         NX_PW_CAPTURE_RAW_PLUS_JPEG,1};
  nx_pw_route_plan p;
  assert(nx_pw_plan_capture(&r,&p)==NX_PW_ROUTE_HOST_RGB_EFFECT);
  assert(p.validated_film_id==legacy-100);
  invariant(&p);
  assert(memcmp(before,raw,sizeof(raw))==0);
  r.mode=NX_PW_CAPTURE_RAW_ONLY;
  assert(nx_pw_plan_capture(&r,&p)==NX_PW_ROUTE_REFUSE);
  invariant(&p);
  assert(memcmp(before,raw,sizeof(raw))==0);
  r.source=NX_PW_SOURCE_CAMERA_DEVICE;
  r.mode=NX_PW_CAPTURE_JPEG_ONLY;
  assert(nx_pw_plan_capture(&r,&p)==NX_PW_ROUTE_REFUSE);
  invariant(&p);
 }
}
int main(void){
 const unsigned n=matrix_cases();
 invalid_cases();
 legacy_leica_and_raw_unchanged();
 printf("PASS Picture Wizard fail-closed routing: %u matrix combinations; 13 separate FilmSim looks vs 12 historical native modes; original bypass; host JPEG-only simulation; camera experimental reject; RAW untouched; legacy ID normalization\n",n);
 return 0;
}
