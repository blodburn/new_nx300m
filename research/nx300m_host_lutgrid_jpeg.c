#include "nx300m_host_lutgrid_jpeg.h"
#include "nx300m_preview_rgb.h"
#include "nx300m_host_jpeg_sink.h"
#include <stdlib.h>
#include <stdint.h>

enum { MAX_DIMENSION=8192 };
#define MAX_HOST_RGB_BYTES ((uint64_t)64u*1024u*1024u)

int nx_host_rgb888_lutgrid_jpeg(
 const uint8_t *rgb,size_t rgb_bytes,size_t rgb_stride,
 unsigned w,unsigned h,const nx_rgb12 *lut,unsigned grid,
 int original_bypass,const char *dest,
 const uint8_t *exif,size_t exif_size){
 if(!rgb||!dest||!dest[0]||!w||!h||
    w>MAX_DIMENSION||h>MAX_DIMENSION||grid<2||grid>65||
    rgb_stride<(size_t)w*3u||
    (uint64_t)w*h*3u>MAX_HOST_RGB_BYTES||
    (uint64_t)(h-1u)*rgb_stride+(uint64_t)w*3u>rgb_bytes)
  return -1;
 /* Original deliberately bypasses the independent JPEG encoder. */
 if(original_bypass)return 1;
 if(!lut)return -1;
 const size_t row_bytes=(size_t)w*3u;
 nx_preview_processor *preview=malloc(sizeof(*preview));
 uint8_t *row=malloc(row_bytes);
 if(!preview||!row||nx_preview_init(preview)!=0){
  free(preview);free(row);return -1;
 }
 nx_host_jpeg_writer *writer=nx_host_jpeg_writer_create_with_sampling(
                       dest,exif,exif_size,NX_HOST_JPEG_420);
 if(!writer){free(preview);free(row);return -1;}
 nx_bayer_rgb8_sink sink=nx_host_jpeg_writer_sink(writer);
 int failed=sink.begin(sink.user,w,h,1)!=0;
 for(unsigned y=0;y<h&&!failed;y++){
  const uint8_t *source=rgb+(size_t)y*rgb_stride;
  for(unsigned x=0;x<w;x++){
   const uint8_t *v=source+3u*x;
   nx_rgb12 in={preview->decode_srgb[v[0]],
                preview->decode_srgb[v[1]],
                preview->decode_srgb[v[2]],0},out;
   if(nx_lut_grid_host_apply(lut,grid,&in,&out,1)!=0){
    failed=1;break;
   }
   row[x*3u]=preview->encode_srgb[out.r>4095u?4095u:out.r];
   row[x*3u+1u]=preview->encode_srgb[out.g>4095u?4095u:out.g];
   row[x*3u+2u]=preview->encode_srgb[out.b>4095u?4095u:out.b];
  }
  if(!failed&&sink.write_row(sink.user,y,row,row_bytes)!=0)failed=1;
 }
 if(!failed&&sink.commit(sink.user)!=0)failed=1;
 if(failed)sink.abort(sink.user);
 nx_host_jpeg_writer_destroy(writer);
 free(row);
 free(preview);
 return failed?-1:0;
}
