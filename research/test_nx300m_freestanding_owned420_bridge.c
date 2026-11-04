/* OFFLINE reference-vs-freestanding Y/C420 copy hypothesis regression.
 * No live NX300M buffer, capture callback, or firmware write.
 * Host-only GNU libc is permitted in the TEST HARNESS, not the DSO.
 */
#include "nx300m_freestanding_owned420_bridge.h"
#include "nx300m_lut_grid_host.h"
#include "nx300m_preview_rgb.h"
#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef int (*render_fn)(const nx_film_owned420_hypothesis_job*);
typedef int (*rows_fn)(const nx_film_owned420_hypothesis_job*,unsigned,unsigned);
static uint8_t sat8(int v){return (uint8_t)(v<0?0:v>255?255:v);}
static void reference_decode(unsigned lum,unsigned cb,unsigned cr,uint8_t rgb[3]){
 const int dcb=(int)cb-128,dcr=(int)cr-128;
 rgb[0]=sat8((int)lum+((91881*dcr+32768)>>16));
 rgb[1]=sat8((int)lum-((22554*dcb+46802*dcr+32768)>>16));
 rgb[2]=sat8((int)lum+((116130*dcb+32768)>>16));
}
static void reference(const nx_film_owned420_hypothesis_job *j,uint8_t *dst){
 for(unsigned yy=0;yy<j->height;yy++){
  const uint8_t *yr=j->y+(size_t)yy*j->y_stride;
  const uint8_t *c=j->chroma+(size_t)(yy/2u)*j->chroma_stride;
  uint8_t *row=dst+(size_t)yy*j->rgb_stride;
  for(unsigned x=0;x<j->width;x++){
   const unsigned pair=x&~1u;
   const unsigned cb=c[pair+
     (j->hypothesis==NX_FILM_BT601_FULL_CRCB_HYPOTHESIS?1u:0u)];
   const unsigned cr=c[pair+
     (j->hypothesis==NX_FILM_BT601_FULL_CRCB_HYPOTHESIS?0u:1u)];
   uint8_t input_rgb[3];
   reference_decode(yr[x],cb,cr,input_rgb);
   nx_rgb12 in={j->decode_srgb[input_rgb[0]],
                j->decode_srgb[input_rgb[1]],
                j->decode_srgb[input_rgb[2]],0u},out;
   assert(nx_lut_grid_host_apply(j->lut,j->grid,&in,&out,1u)==0);
   row[(size_t)x*3u]=j->encode_srgb[out.r>4095u?4095u:out.r];
   row[(size_t)x*3u+1u]=j->encode_srgb[out.g>4095u?4095u:out.g];
   row[(size_t)x*3u+2u]=j->encode_srgb[out.b>4095u?4095u:out.b];
  }
 }
}
static void test_one(render_fn render,rows_fn render_rows,
                     unsigned grid,unsigned order){
 enum { W=12,H=8,YSTRIDE=16,CSTRIDE=18,RSTRIDE=42 };
 const size_t count=(size_t)grid*grid*grid;
 nx_rgb12 *lut=malloc(count*sizeof(*lut));
 assert(lut!=NULL);
 for(unsigned b=0;b<grid;b++)
  for(unsigned g=0;g<grid;g++)
   for(unsigned r=0;r<grid;r++){
    const size_t index=((size_t)b*grid+g)*grid+r;
    nx_rgb12 *pixel=&lut[index];
    pixel->r=(uint16_t)((r*3500u+(grid-1u)/2u)/(grid-1u));
    pixel->g=(uint16_t)((g*3900u+(grid-1u)/2u)/(grid-1u));
    pixel->b=(uint16_t)((b*3500u+(grid-1u)/2u)/(grid-1u));
    pixel->reserved=0u;
   }
 uint8_t y[YSTRIDE*H],c[CSTRIDE*(H/2u)];
 uint8_t yoriginal[sizeof(y)],coriginal[sizeof(c)];
 uint8_t output[RSTRIDE*H],expected[RSTRIDE*H],guard[RSTRIDE*H];
 for(unsigned row=0;row<H;row++){
  for(unsigned x=0;x<YSTRIDE;x++)
   y[(size_t)row*YSTRIDE+x]=
      (uint8_t)((x<W)?(19u+x*17u+row*13u)%256u:0xa5u);
 }
 for(unsigned row=0;row<H/2u;row++){
  for(unsigned x=0;x<CSTRIDE;x++)
   c[(size_t)row*CSTRIDE+x]=
      (uint8_t)((x<W)?(32u+x*23u+row*41u)%256u:0x5au);
 }
 memcpy(yoriginal,y,sizeof(y));memcpy(coriginal,c,sizeof(c));
 memset(output,0xcc,sizeof(output));
 memset(expected,0xcc,sizeof(expected));
 nx_preview_processor preview;
 assert(nx_preview_init(&preview)==0);
 nx_film_owned420_hypothesis_job j={
    .copy_declaration=NX_FILM_420_COPY_DECLARATION,
    .hypothesis=order,
    .y=y,.y_bytes=sizeof(y),.y_stride=YSTRIDE,
    .chroma=c,.chroma_bytes=sizeof(c),.chroma_stride=CSTRIDE,
    .width=W,.height=H,
    .decode_srgb=preview.decode_srgb,
    .decode_entries=256u,
    .encode_srgb=preview.encode_srgb,
    .encode_entries=4096u,
    .lut=lut,.lut_nodes=count,.grid=grid,
    .rgb=output,.rgb_bytes=sizeof(output),.rgb_stride=RSTRIDE,
 };
 reference(&j,expected);
 assert(render(&j)==0);
 assert(memcmp(output,expected,sizeof(output))==0);
 /* A single-row output uses only the caller's small RGB stripe, while
  * chroma index is always computed from the GLOBAL image row number.
  * Odd first_row and partial final stripe are intentional regressions.
  */
 uint8_t striped[RSTRIDE*H],striped_before[RSTRIDE*H];
 nx_film_owned420_hypothesis_job r=j;
 memset(striped,0xcc,sizeof(striped));
 for(unsigned first=0;first<H;first++){
  r.rgb=striped+(size_t)first*RSTRIDE;
  r.rgb_bytes=W*3u;
  assert(render_rows(&r,first,1u)==0);
 }
 assert(memcmp(striped,expected,sizeof(striped))==0);
 memset(striped,0xcc,sizeof(striped));
 for(unsigned first=0;first<H;first+=3u){
  const unsigned count=H-first<3u?H-first:3u;
  r.rgb=striped+(size_t)first*RSTRIDE;
  r.rgb_bytes=(size_t)(count-1u)*RSTRIDE+W*3u;
  assert(render_rows(&r,first,count)==0);
 }
 assert(memcmp(striped,expected,sizeof(striped))==0);
 memset(striped,0xcc,sizeof(striped));
 memcpy(striped_before,striped,sizeof(striped));
 for(unsigned bad=0;bad<9u;bad++){
  unsigned first=1u,rows=1u;
  r=j;
  r.rgb=striped;
  r.rgb_bytes=sizeof(striped);
  switch(bad){
   case 0:first=H;break;
   case 1:rows=0u;break;
   case 2:first=H-1u;rows=2u;break;
   case 3:r.rgb_bytes=W*3u-1u;break;
   case 4:r.rgb=(uint8_t*)j.y;break;
   case 5:r.rgb=(uint8_t*)j.chroma;break;
   case 6:r.hypothesis=0u;break;
   case 7:r.height=H-1u;break;
   case 8:r.decode_entries=0u;break;
  }
  assert(render_rows(&r,first,rows)==-1);
  assert(memcmp(striped,striped_before,sizeof(striped))==0);
 }
 /* Failed row jobs must not corrupt immutable input planes either. */
 assert(memcmp(y,yoriginal,sizeof(y))==0);
 assert(memcmp(c,coriginal,sizeof(c))==0);
 assert(memcmp(y,yoriginal,sizeof(y))==0);
 assert(memcmp(c,coriginal,sizeof(c))==0);
 for(unsigned row=0;row<H;row++)
  for(unsigned x=W*3u;x<RSTRIDE;x++)
   assert(output[(size_t)row*RSTRIDE+x]==0xccu);
 nx_film_owned420_hypothesis_job k=j;
 /* Invalid jobs MUST NOT mutate output or either input. */
 const unsigned invalids=11u;
 for(unsigned v=0;v<invalids;v++){
  memcpy(guard,output,sizeof(guard));
  k=j;
  switch(v){
   case 0:k.copy_declaration=0u;break;
   case 1:k.hypothesis=0u;break;
   case 2:k.width=W-1u;break;
   case 3:k.y_bytes=W;break;
   case 4:k.chroma_bytes=W;break;
   case 5:k.rgb_bytes=W*3u;break;
   case 6:k.lut_nodes=count-1u;break;
   case 7:k.decode_entries=255u;break;
   case 8:k.encode_entries=4095u;break;
   case 9:k.rgb=(uint8_t*)j.y;k.rgb_bytes=sizeof(output);break;
   case 10:k.rgb=(uint8_t*)j.chroma;k.rgb_bytes=sizeof(output);break;
  }
  assert(render(&k)==-1);
  assert(memcmp(output,guard,sizeof(output))==0);
 }
 assert(memcmp(y,yoriginal,sizeof(y))==0);
 assert(memcmp(c,coriginal,sizeof(c))==0);
 free(lut);
 printf("PASS owned420 GLIBC-free bridge: grid=%u order=%u, "
        "96 synthetic pixels, exact host parity, one-row and three-row "
        "stripes, invalid spans + padding + read-only planes\n",grid,order);
}
/* 20.6MP geometry gate: bounded one-row RGB output, not a camera
 * memory benchmark or a claim about NX300M native strides/format.
 */
static void test_full_geometry(rows_fn render_rows){
 enum { W=5546,H=3714,PAD=8 };
 const size_t yn=(size_t)W*H,cn=yn/2u;
 const size_t stride=(size_t)W*3u+PAD;
 uint8_t *y=malloc(yn),*c=malloc(cn),*rgb=malloc(stride);
 assert(y&&c&&rgb);
 memset(y,111,yn);
 memset(c,151,cn);
 nx_rgb12 lut[8];
 for(unsigned b=0;b<2u;b++)
  for(unsigned g=0;g<2u;g++)
   for(unsigned r=0;r<2u;r++){
    const size_t k=(size_t)b*4u+(size_t)g*2u+r;
    lut[k]=(nx_rgb12){r?4095u:0u,g?4095u:0u,b?4095u:0u,0u};
   }
 nx_preview_processor preview;
 assert(nx_preview_init(&preview)==0);
 nx_film_owned420_hypothesis_job j={
    .copy_declaration=NX_FILM_420_COPY_DECLARATION,
    .hypothesis=NX_FILM_BT601_FULL_CBCR_HYPOTHESIS,
    .y=y,.y_bytes=yn,.y_stride=W,
    .chroma=c,.chroma_bytes=cn,.chroma_stride=W,
    .width=W,.height=H,
    .decode_srgb=preview.decode_srgb,.decode_entries=256u,
    .encode_srgb=preview.encode_srgb,.encode_entries=4096u,
    .lut=lut,.lut_nodes=8u,.grid=2u,
    .rgb=rgb,.rgb_bytes=stride,.rgb_stride=stride,
 };
 uint8_t decoded[3];
 reference_decode(111u,151u,151u,decoded);
 nx_rgb12 in={preview.decode_srgb[decoded[0]],
              preview.decode_srgb[decoded[1]],
              preview.decode_srgb[decoded[2]],0u},out;
 assert(nx_lut_grid_host_apply(lut,2u,&in,&out,1u)==0);
 const uint8_t want[3]={preview.encode_srgb[out.r],
                         preview.encode_srgb[out.g],
                         preview.encode_srgb[out.b]};
 const unsigned rows[]={0u,1u,H-2u,H-1u};
 for(unsigned k=0;k<sizeof(rows)/sizeof(rows[0]);k++){
  memset(rgb,0xcc,stride);
  assert(render_rows(&j,rows[k],1u)==0);
  for(unsigned x=0;x<W;x++)
   for(unsigned ch=0;ch<3u;ch++)
    assert(rgb[(size_t)x*3u+ch]==want[ch]);
  for(size_t x=(size_t)W*3u;x<stride;x++)
   assert(rgb[x]==0xccu);
 }
 memset(rgb,0xcc,stride);
 j.rgb_bytes=(size_t)W*3u-1u;
 assert(render_rows(&j,H-1u,1u)==-1);
 for(size_t x=0;x<stride;x++)assert(rgb[x]==0xccu);
 assert(y[0]==111u&&y[yn-1u]==111u&&c[0]==151u&&c[cn-1u]==151u);
 free(rgb);free(c);free(y);
 printf("PASS owned420 5546x3714: full geometry, 16638-byte output row, "
        "first/last odd/even indices, stride guards and fail-closed bounds\\n");
}

int main(int argc,char **argv){
 assert(argc==2);
 void *h=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);
 if(!h){
  fprintf(stderr,"cannot load host-only DSO: %s\n",dlerror());
  return 2;
 }
 void *pointer=dlsym(h,"nx_film_core_render_owned420_hypothesis");
 assert(pointer);
 render_fn render=(render_fn)pointer;
 pointer=dlsym(h,"nx_film_core_render_owned420_rows_hypothesis");
 assert(pointer);
 rows_fn render_rows=(rows_fn)pointer;
 test_full_geometry(render_rows);
 for(unsigned grid=2u;grid<=65u;grid=(grid==2u?18u:66u))
  for(unsigned order=1u;order<=2u;order++)
   test_one(render,render_rows,grid,order);
 /* Test 65-grid separately (loop above is bounded, explicit). */
 for(unsigned order=1u;order<=2u;order++)
  test_one(render,render_rows,65u,order);
 assert(dlclose(h)==0);
 puts("PASS GLIBC-FREE owned Y/C420 copy hypothesis -> RGB12 LUT "
      "-> RGB888; no camera ISP/JPEG claims");
 return 0;
}
