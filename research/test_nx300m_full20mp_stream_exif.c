#define _POSIX_C_SOURCE 200809L
/* SYNTHETIC 20.6MP HOST REGRESSION ONLY.
 * No camera buffers, Samsung JPEG, live capture, firmware or RAW.
 * Verifies independent no-libc row streaming at sensor-sized geometry.
 */
#include "nx300m_host_freestanding420_jpeg.h"
#include "nx300m_preview_rgb.h"
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

enum { WIDTH=5546u,HEIGHT=3714u,Y_STRIDE=WIDTH+16u,C_STRIDE=WIDTH+16u };
static const uint8_t synthetic_app1[]={
 'E','x','i','f',0,0,'I','I',42,0,8,0,0,0,
 1,0,
 0x69,0x87,4,0,1,0,0,0,26,0,0,0,
 0,0,0,0,
 1,0,
 0x7c,0x92,7,0,8,0,0,0,44,0,0,0,
 0,0,0,0,
 'N','X','-','M','A','K','E','R'
};
/* FNV-1a is a mutation detector ONLY, never a provenance/authentication hash. */
static uint64_t fingerprint(const void *p,size_t n){
 const uint8_t *data=p;
 uint64_t value=UINT64_C(14695981039346656037);
 for(size_t i=0;i<n;i++){
  value^=data[i];
  value*=UINT64_C(1099511628211);
 }
 return value;
}
static double elapsed(struct timespec first,struct timespec second){
 return (double)(second.tv_sec-first.tv_sec)
    +1e-9*(double)(second.tv_nsec-first.tv_nsec);
}
static void fill(uint8_t *y,uint8_t *c){
 for(unsigned row=0;row<HEIGHT;row++){
  uint8_t *dest=y+(size_t)row*Y_STRIDE;
  for(unsigned x=0;x<WIDTH;x++)
   dest[x]=(uint8_t)((x/3u*17u+row/5u*11u+(x*row/97u))&255u);
  memset(dest+WIDTH,0xa5,Y_STRIDE-WIDTH);
 }
 for(unsigned row=0;row<HEIGHT/2u;row++){
  uint8_t *dest=c+(size_t)row*C_STRIDE;
  for(unsigned x=0;x<WIDTH;x+=2u){
   dest[x]=(uint8_t)((51u+x/3u+row*3u)&255u);
   dest[x+1]=(uint8_t)((197u+x/7u+row*5u)&255u);
  }
  memset(dest+WIDTH,0xc3,C_STRIDE-WIDTH);
 }
}
static nx_rgb12 identity[8];
static void init_identity(void){
 for(unsigned b=0;b<2u;b++)
  for(unsigned g=0;g<2u;g++)
   for(unsigned r=0;r<2u;r++)
    identity[4u*b+2u*g+r]=(nx_rgb12){
     (uint16_t)(r*4095u),(uint16_t)(g*4095u),
     (uint16_t)(b*4095u),0u
    };
}
static nx_rgb12 *init_study_lut65(void){
 enum { GRID=65u };
 const size_t n=(size_t)GRID*GRID*GRID;
 nx_rgb12 *lut=malloc(n*sizeof(*lut));
 if(!lut)return NULL;
 for(unsigned b=0;b<GRID;b++)
  for(unsigned g=0;g<GRID;g++)
   for(unsigned r=0;r<GRID;r++){
    unsigned red=r*4095u/64u;
    unsigned green=g*4095u/64u;
    unsigned blue=b*4095u/64u;
    lut[((size_t)b*GRID+g)*GRID+r]=(nx_rgb12){
      (uint16_t)((red*84u+blue*16u)/100u),
      (uint16_t)((green*88u+red*12u)/100u),
      (uint16_t)((blue*89u+green*11u)/100u),
      0u
    };
   }
 return lut;
}
static void usage(void){
 fputs("usage: test_nx300m_full20mp_stream_exif MODULE BASELINE_JPG FILM_JPG\n"
       "HOST ONLY: synthetic Y/C, NOT Samsung NX300M camera input.\n",stderr);
}
int main(int argc,char **argv){
 if(argc!=4||!argv[1]||!argv[2]||!argv[3]){usage();return 2;}
 if(!strcmp(argv[2],argv[3])||!strcmp(argv[1],argv[2])||
    !strcmp(argv[1],argv[3]))return 2;
 if(access(argv[2],F_OK)==0||access(argv[3],F_OK)==0){
  fputs("REJECT: output exists\n",stderr);return 2;
 }
 const size_t y_len=(size_t)Y_STRIDE*HEIGHT;
 const size_t c_len=(size_t)C_STRIDE*(HEIGHT/2u);
 uint8_t *y=malloc(y_len),*c=malloc(c_len);
 nx_rgb12 *lut65=init_study_lut65();
 if(!y||!c||!lut65){
  fputs("REJECT: host allocation\n",stderr);
  free(y);free(c);free(lut65);return 2;
 }
 fill(y,c);init_identity();
 const uint64_t hy=fingerprint(y,y_len),hc=fingerprint(c,c_len);
 const uint64_t hl=fingerprint(lut65,65u*65u*65u*sizeof(*lut65));
 nx_preview_processor preview;
 if(nx_preview_init(&preview)!=0){
  free(y);free(c);free(lut65);return 2;
 }
 nx_film_owned420_hypothesis_job j={0};
 j.copy_declaration=NX_FILM_420_COPY_DECLARATION;
 j.hypothesis=NX_FILM_BT601_FULL_CBCR_HYPOTHESIS;
 j.y=y;j.y_bytes=y_len;j.y_stride=Y_STRIDE;
 j.chroma=c;j.chroma_bytes=c_len;j.chroma_stride=C_STRIDE;
 j.width=WIDTH;j.height=HEIGHT;
 j.decode_srgb=preview.decode_srgb;j.decode_entries=256u;
 j.encode_srgb=preview.encode_srgb;j.encode_entries=4096u;
 j.lut=identity;j.lut_nodes=8u;j.grid=2u;
 struct timespec start,mid,end;
 if(clock_gettime(CLOCK_MONOTONIC,&start)!=0)return 2;
 if(nx_host_freestanding420_jpeg_copy(argv[1],&j,0,argv[2],
      synthetic_app1,sizeof(synthetic_app1))!=0){
  fputs("REJECT: baseline JPEG stream\n",stderr);
  free(y);free(c);free(lut65);return 1;
 }
 if(clock_gettime(CLOCK_MONOTONIC,&mid)!=0)return 2;
 j.lut=lut65;j.lut_nodes=65u*65u*65u;j.grid=65u;
 if(nx_host_freestanding420_jpeg_copy(argv[1],&j,0,argv[3],
      synthetic_app1,sizeof(synthetic_app1))!=0){
  fputs("REJECT: Film LUT65 JPEG stream\n",stderr);
  free(y);free(c);free(lut65);return 1;
 }
 if(clock_gettime(CLOCK_MONOTONIC,&end)!=0)return 2;
 /* Fail closed if caller-owned copies or LUT nodes were modified. */
 if(fingerprint(y,y_len)!=hy||fingerprint(c,c_len)!=hc||
    fingerprint(lut65,65u*65u*65u*sizeof(*lut65))!=hl){
  fputs("REJECT: input plane or LUT was changed\n",stderr);
  free(y);free(c);free(lut65);return 1;
 }
 /* Both outputs must already exist. A second request must never overwrite. */
 if(nx_host_freestanding420_jpeg_copy(argv[1],&j,0,argv[3],
        synthetic_app1,sizeof(synthetic_app1))!=-1){
  fputs("REJECT: attempted JPEG destination overwrite\n",stderr);
  free(y);free(c);free(lut65);return 1;
 }
 struct rusage ru;
 if(getrusage(RUSAGE_SELF,&ru)!=0){
  free(y);free(c);free(lut65);return 2;
 }
 printf("NX300M_FULL20MP_JSON {"
        "\"host_only\":true,"
        "\"firmware_flash_safe\":false,"
        "\"on_device_20mp_verified\":false,"
        "\"width\":%u,\"height\":%u,"
        "\"pixel_count\":%ju,"
        "\"baseline_grid\":2,\"film_grid\":65,"
        "\"y_bytes\":%zu,\"c_bytes\":%zu,"
        "\"lut65_bytes\":%zu,"
        "\"peak_rss_kib\":%ld,"
        "\"baseline_seconds\":%.3f,\"film_seconds\":%.3f,"
        "\"input_planes_and_lut_unchanged\":true,"
        "\"destination_overwrite_blocked\":true,"
        "\"exif_synthetic_only\":true}\n",
        WIDTH,HEIGHT,(uintmax_t)WIDTH*HEIGHT,y_len,c_len,
        (size_t)65u*65u*65u*sizeof(*lut65),
        ru.ru_maxrss,elapsed(start,mid),elapsed(mid,end));
 free(y);free(c);free(lut65);
 return 0;
}
