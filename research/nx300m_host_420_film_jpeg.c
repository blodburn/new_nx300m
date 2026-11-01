#include "nx300m_host_420_film_jpeg.h"
#include "nx300m_image_enhance.h"
#include "nx300m_camera_style_response.h"
#include "nx300m_preview_rgb.h"
#include "nx300m_host_jpeg_sink.h"
#include "nx300m_film_menu.h"
#include <stdint.h>
#include <stdlib.h>
#include <limits.h>

enum { MAX_DIMENSION=8192, MAX_STRIDE=65536 };
#define MAX_HOST_FRAME_BYTES ((size_t)64u*1024u*1024u)

static uint8_t byte8(int x){
 return (uint8_t)(x<0?0:x>255?255:x);
}
static void decode_pixel(unsigned yy,unsigned cbb,unsigned crr,
                         uint8_t *out){
 int cb=(int)cbb-128,cr=(int)crr-128,y=(int)yy;
 /* HOST BT.601 full-range conversion only; native Samsung ISP matrix,
  * chroma siting, luma range and layout remain unverified. */
 out[0]=byte8(y+((91881*cr+32768)>>16));
 out[1]=byte8(y-((22554*cb+46802*cr+32768)>>16));
 out[2]=byte8(y+((116130*cb+32768)>>16));
}
int nx_host420_film_to_jpeg(
    const uint8_t *y,size_t y_bytes,size_t y_stride,
    const uint8_t *chroma,size_t chroma_bytes,size_t chroma_stride,
    unsigned w,unsigned h,enum nx_host420_order order,
    unsigned film_id,const char *destination,
    const uint8_t *original_exif,size_t exif_size){
 const nx_film_preset *film=nx_film_by_id(film_id);
 if(!film||!y||!chroma||!destination||!destination[0]||
    w<4u||h<4u||w>MAX_DIMENSION||h>MAX_DIMENSION||
    (w&1u)||(h&1u)||y_stride<w||chroma_stride<w||
    y_stride>MAX_STRIDE||chroma_stride>MAX_STRIDE||
    (order!=NX_HOST420_CBCR_EXPERIMENTAL&&
     order!=NX_HOST420_CRCB_EXPERIMENTAL))return -1;
 const uint64_t last_y=(uint64_t)(h-1u)*y_stride+w;
 const uint64_t last_c=(uint64_t)(h/2u-1u)*chroma_stride+w;
 const uint64_t pixels=(uint64_t)w*h*3u;
 if(last_y>y_bytes||last_c>chroma_bytes||pixels>MAX_HOST_FRAME_BYTES)
    return -1;
 /* "Samsung Original" bypasses the independent image engine and does
  * not silently re-encode an Original image or create a second JPG. */
 if(film->id==0)return 1;
 /* Host pixel pipeline uses only six RGB rows + three luma rows, not
  * W*H*3 RGB frames. All neighborhood stages see their UNMODIFIED input
  * neighbors before the next stage writes its output. */
 const size_t stride=(size_t)w*3u;
 uint8_t *scratch=malloc((size_t)w*21u);
 nx_rgb12 *lut=malloc(sizeof(nx_rgb12)*NX_LUT_COUNT);
 nx_preview_processor *preview=malloc(sizeof(nx_preview_processor));
 if(!scratch||!lut||!preview){
  free(scratch);free(lut);free(preview);return -1;
 }
 nx_film_menu selection;nx_film_menu_init(&selection);
 selection.selected_id=film->id;
 if(nx_film_lut_for_menu(&selection,lut)!=0||nx_preview_init(preview)!=0){
  free(scratch);free(lut);free(preview);return -1;
 }
 uint8_t *filtered[3],*enhanced[3],*luma[3];
 for(unsigned i=0;i<3;i++){
  filtered[i]=scratch+(size_t)i*stride;
  enhanced[i]=scratch+(size_t)(3u+i)*stride;
  luma[i]=scratch+6u*stride+(size_t)i*w;
 }
 /* Create-only writer atomically publishes a single completed JPEG.
  * The encoder receives HOST RGB, never Samsung native Y/C DMA. */
 nx_host_jpeg_writer *writer=nx_host_jpeg_writer_create_with_sampling(
      destination,original_exif,exif_size,NX_HOST_JPEG_420);
 if(!writer){free(scratch);free(lut);free(preview);return -1;}
 nx_bayer_rgb8_sink sink=nx_host_jpeg_writer_sink(writer);
 int status=sink.begin(sink.user,w,h,film->id)!=0?-1:0;
 for(unsigned k=0;k<=h&&!status;k++){
  if(k<h){
   const uint8_t *yy=y+(size_t)k*y_stride;
   const uint8_t *cc=chroma+(size_t)(k/2u)*chroma_stride;
   uint8_t *dest=filtered[k%3u];
   for(unsigned x=0;x<w;x++){
    const unsigned pair=x&~1u;
    const unsigned cb=cc[pair+(order==NX_HOST420_CRCB_EXPERIMENTAL?1u:0u)];
    const unsigned cr=cc[pair+(order==NX_HOST420_CRCB_EXPERIMENTAL?0u:1u)];
    decode_pixel(yy[x],cb,cr,dest+3u*x);
   }
   if(nx_preview_filter_rgb888(preview,lut,dest,stride,dest,stride,w,1)!=0)
    status=-1;
  }
  if(!status&&k>=1u){
   const unsigned center=k-1u;
   const uint8_t *before=center?filtered[(center-1u)%3u]:NULL;
   const uint8_t *after=center+1u<h?filtered[(center+1u)%3u]:NULL;
   if(nx_image_enhance_rgb888_row(before,filtered[center%3u],after,
       enhanced[center%3u],w,center,h)!=0||
      nx_camera_style_luma_row(enhanced[center%3u],w,luma[center%3u])!=0)
    status=-1;
  }
  if(!status&&k>=2u){
   const unsigned row=k-2u;
   if(nx_camera_style_apply_row(film->id,enhanced[row%3u],w,row,h,
         row?luma[(row-1u)%3u]:NULL,luma[row%3u],luma[(row+1u)%3u])!=0||
      sink.write_row(sink.user,row,enhanced[row%3u],stride)!=0)
    status=-1;
  }
 }
 if(!status&&
    (nx_camera_style_apply_row(film->id,enhanced[(h-1u)%3u],w,h-1u,h,
         luma[(h-2u)%3u],luma[(h-1u)%3u],NULL)!=0||
     sink.write_row(sink.user,h-1u,enhanced[(h-1u)%3u],stride)!=0))status=-1;
 if(!status&&sink.commit(sink.user)!=0)status=-1;
 if(status)sink.abort(sink.user);
 nx_host_jpeg_writer_destroy(writer);
 free(scratch);free(lut);free(preview);
 return status;
}
