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
static void test_one(render_fn render,unsigned grid,unsigned order){
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
        "96 synthetic pixels, exact host color parity, guard + padding + "
        "read-only planes\n",grid,order);
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
 for(unsigned grid=2u;grid<=65u;grid=(grid==2u?18u:66u))
  for(unsigned order=1u;order<=2u;order++)
   test_one(render,grid,order);
 /* Test 65-grid separately (loop above is bounded, explicit). */
 for(unsigned order=1u;order<=2u;order++)
  test_one(render,65u,order);
 assert(dlclose(h)==0);
 puts("PASS GLIBC-FREE owned Y/C420 copy hypothesis -> RGB12 LUT "
      "-> RGB888; no camera ISP/JPEG claims");
 return 0;
}
