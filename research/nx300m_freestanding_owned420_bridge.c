#include "nx300m_freestanding_owned420_bridge.h"
#include <stdint.h>

/* All multiplication is bounded by width/height/stride <= 8192/65536.
 * No C library, float, heap or I/O. Only owned-copied plane assumptions.
 * A caller can lie about pointer provenance; no physical camera attestation.
 */
static uint8_t sat8(int value){
 return (uint8_t)(value<0?0:value>255?255:value);
}
static void decode601(unsigned y,unsigned cb,unsigned cr,uint8_t rgb[3]){
 const int cc=(int)cb-128,rr=(int)cr-128,lum=(int)y;
 rgb[0]=sat8(lum+((91881*rr+32768)>>16));
 rgb[1]=sat8(lum-((22554*cc+46802*rr+32768)>>16));
 rgb[2]=sat8(lum+((116130*cc+32768)>>16));
}
static int overlaps(const void *a,size_t an,const void *b,size_t bn){
 const uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
 if(an>UINTPTR_MAX-x||bn>UINTPTR_MAX-y)return 1;
 return x<y+bn&&y<x+an;
}
static int preflight(const nx_film_owned420_hypothesis_job *j,
                     unsigned first_row, unsigned rows){
 if(!j||j->copy_declaration!=NX_FILM_420_COPY_DECLARATION||
    (j->hypothesis!=NX_FILM_BT601_FULL_CBCR_HYPOTHESIS&&
     j->hypothesis!=NX_FILM_BT601_FULL_CRCB_HYPOTHESIS)||
    !j->y||!j->chroma||!j->lut||!j->rgb||
    !j->decode_srgb||!j->encode_srgb||
    j->width<4u||j->height<4u||
    j->width>8192u||j->height>8192u||
    (j->width&1u)||(j->height&1u)||
    j->grid<2u||j->grid>65u||
    j->decode_entries!=256u||j->encode_entries!=4096u||
    j->lut_nodes<(size_t)j->grid*j->grid*j->grid||
    j->y_stride<j->width||j->chroma_stride<j->width||
    j->rgb_stride<(size_t)j->width*3u||
    j->y_stride>65536u||j->chroma_stride>65536u||
    j->rgb_stride>65536u||
    first_row>=j->height||rows==0u||
    rows>j->height-first_row)return -1;
 const size_t yn=(size_t)(j->height-1u)*j->y_stride+j->width;
 const size_t cn=(size_t)(j->height/2u-1u)*j->chroma_stride+j->width;
 const size_t rn=(size_t)(rows-1u)*j->rgb_stride+
                 (size_t)j->width*3u;
 const size_t lut_len=(size_t)j->grid*j->grid*j->grid*sizeof(nx_rgb12);
 if(yn>j->y_bytes||cn>j->chroma_bytes||rn>j->rgb_bytes||
    j->lut_nodes>SIZE_MAX/sizeof(nx_rgb12))return -1;
 /* Output must not alias any source/lookup buffer or the job struct.
  * This supports atomic rejection of bad metadata, but not memory faults
  * caused by a caller supplying an invalid/misrepresented pointer.
  */
 if(overlaps(j->rgb,rn,j->y,yn)||
    overlaps(j->rgb,rn,j->chroma,cn)||
    overlaps(j->rgb,rn,j->lut,lut_len)||
    overlaps(j->rgb,rn,j->decode_srgb,256u*sizeof(uint16_t))||
    overlaps(j->rgb,rn,j->encode_srgb,4096u)||
    overlaps(j->rgb,rn,j,sizeof(*j)))return -1;
 for(unsigned i=0;i<256u;i++)
  if(j->decode_srgb[i]>4095u)return -1;
 return 0;
}
static int render_rows(const nx_film_owned420_hypothesis_job *j,
                       unsigned first_row,unsigned rows){
 if(preflight(j,first_row,rows)!=0)return -1;
 for(unsigned row=first_row;row<first_row+rows;row++){
  const uint8_t *yp=j->y+(size_t)row*j->y_stride;
  const uint8_t *cp=j->chroma+(size_t)(row/2u)*j->chroma_stride;
  uint8_t *target=j->rgb+(size_t)(row-first_row)*j->rgb_stride;
  for(unsigned x=0;x<j->width;x++){
   const unsigned pair=x&~1u;
   const unsigned cb=cp[pair+
       (j->hypothesis==NX_FILM_BT601_FULL_CRCB_HYPOTHESIS?1u:0u)];
   const unsigned cr=cp[pair+
       (j->hypothesis==NX_FILM_BT601_FULL_CRCB_HYPOTHESIS?0u:1u)];
   uint8_t pixel[3];
   decode601(yp[x],cb,cr,pixel);
   const nx_rgb12 in={
      j->decode_srgb[pixel[0]],
      j->decode_srgb[pixel[1]],
      j->decode_srgb[pixel[2]],0u
   };
   nx_rgb12 out;
   if(nx_film_core_apply_rgb12(j->lut,j->lut_nodes,j->grid,
                               &in,&out,1u)!=0)return -1;
   target[(size_t)x*3u+0u]=j->encode_srgb[out.r>4095u?4095u:out.r];
   target[(size_t)x*3u+1u]=j->encode_srgb[out.g>4095u?4095u:out.g];
   target[(size_t)x*3u+2u]=j->encode_srgb[out.b>4095u?4095u:out.b];
  }
 }
 return 0;
}

/* Backward-compatible full-frame export: original job ABI is unchanged. */
int nx_film_core_render_owned420_hypothesis(
    const nx_film_owned420_hypothesis_job *j){
 return render_rows(j,0u,j?j->height:0u);
}

/* A stripe output pointer always starts at its first local RGB row.
 * No retention, dynamic memory, callbacks or native JPEG calls.
 */
int nx_film_core_render_owned420_rows_hypothesis(
    const nx_film_owned420_hypothesis_job *j,
    unsigned first_row,unsigned row_count){
 return render_rows(j,first_row,row_count);
}
