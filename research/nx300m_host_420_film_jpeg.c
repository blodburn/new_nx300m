#include "nx300m_host_420_film_jpeg.h"
#include "nx300m_still_enhanced.h"
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
 const size_t stride=(size_t)w*3u;
 const size_t bytes=stride*h;
 uint8_t *rgb=malloc(bytes);
 if(!rgb)return -1;
 for(unsigned row=0;row<h;row++){
  const uint8_t *yy=y+(size_t)row*y_stride;
  const uint8_t *cc=chroma+(size_t)(row/2u)*chroma_stride;
  uint8_t *dest=rgb+(size_t)row*stride;
  for(unsigned x=0;x<w;x++){
   const unsigned pair=x&~1u;
   const unsigned cb=cc[pair+(order==NX_HOST420_CRCB_EXPERIMENTAL?1u:0u)];
   const unsigned cr=cc[pair+(order==NX_HOST420_CRCB_EXPERIMENTAL?0u:1u)];
   decode_pixel(yy[x],cb,cr,dest+3u*x);
  }
 }
 const int result=nx_still_filter_enhanced_inplace(film->id,
                       NX_STILL_SRGB_RGB888,rgb,stride,w,h);
 if(result!=NX_STILL_APPLIED){free(rgb);return -1;}
 /* Create-only writer atomically publishes a single completed JPEG.
  * The encoder receives HOST RGB, never Samsung native Y/C DMA. */
 nx_host_jpeg_writer *writer=nx_host_jpeg_writer_create_with_sampling(
      destination,original_exif,exif_size,NX_HOST_JPEG_420);
 if(!writer){free(rgb);return -1;}
 nx_bayer_rgb8_sink sink=nx_host_jpeg_writer_sink(writer);
 int status=0;
 if(sink.begin(sink.user,w,h,film->id)!=0)status=-1;
 if(!status)for(unsigned row=0;row<h;row++){
  if(sink.write_row(sink.user,row,rgb+(size_t)row*stride,stride)!=0){
   status=-1;break;
  }
 }
 if(!status&&sink.commit(sink.user)!=0)status=-1;
 if(status)sink.abort(sink.user);
 nx_host_jpeg_writer_destroy(writer);
 free(rgb);
 return status;
}
