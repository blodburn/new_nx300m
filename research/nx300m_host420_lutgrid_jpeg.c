#include "nx300m_host420_lutgrid_jpeg.h"
#include "nx300m_preview_rgb.h"
#include "nx300m_host_jpeg_sink.h"
#include <math.h>
#include <stdint.h>
#include <stdlib.h>

enum { MAX_DIMENSION=8192,MAX_STRIDE=65536 };
#define MAX_HOST_RGB_EQUIVALENT ((uint64_t)64u*1024u*1024u)

static uint8_t byte8(int n){return (uint8_t)(n<0?0:n>255?255:n);}
static void decode_host(unsigned y,unsigned cbb,unsigned crr,
                       enum nx_420_model model,uint8_t rgb[3]){
 /* This is a host hypothesis matching the legacy 420 decoder.
  * It is not a discovered Samsung native ISP conversion. */
 if(model!=NX_420_BT601_FULL){
  const int limited=model==NX_420_BT601_LIMITED||
                    model==NX_420_BT709_LIMITED;
  const int bt709=model==NX_420_BT709_FULL||
                  model==NX_420_BT709_LIMITED;
  const double yy=limited?((double)y-16.)*255./219.:(double)y;
  const double chroma_scale=limited?255./224.:1.;
  const double cb=((int)cbb-128)*chroma_scale;
  const double cr=((int)crr-128)*chroma_scale;
  rgb[0]=byte8((int)lround(yy+(bt709?1.5748:1.402)*cr));
  rgb[1]=byte8((int)lround(yy-(bt709?0.187324:0.344136)*cb-
                                (bt709?0.468124:0.714136)*cr));
  rgb[2]=byte8((int)lround(yy+(bt709?1.8556:1.772)*cb));
  return;
 }
 const int cb=(int)cbb-128,cr=(int)crr-128,l=(int)y;
 rgb[0]=byte8(l+((91881*cr+32768)>>16));
 rgb[1]=byte8(l-((22554*cb+46802*cr+32768)>>16));
 rgb[2]=byte8(l+((116130*cb+32768)>>16));
}
int nx_host420_lutgrid_jpeg_hypothesis(
    const uint8_t *y,size_t y_bytes,size_t y_stride,
    const uint8_t *c,size_t c_bytes,size_t c_stride,
    unsigned w,unsigned h,enum nx_host420_order order,
    enum nx_420_model model,const nx_rgb12 *lut,unsigned grid,
    int original_bypass,const char *dest,
    const uint8_t *exif,size_t exif_bytes){
 if(!y||!c||!dest||!dest[0]||w<4||h<4||
    w>MAX_DIMENSION||h>MAX_DIMENSION||
    (w&1u)||(h&1u)||
    y_stride<w||c_stride<w||y_stride>MAX_STRIDE||c_stride>MAX_STRIDE||
    (order!=NX_HOST420_CBCR_EXPERIMENTAL&&
     order!=NX_HOST420_CRCB_EXPERIMENTAL)||
    model<0||model>=NX_420_MODEL_COUNT||
    grid<2||grid>65||
    (uint64_t)w*h*3u>MAX_HOST_RGB_EQUIVALENT||
    (uint64_t)(h-1u)*y_stride+w>y_bytes||
    (uint64_t)(h/2u-1u)*c_stride+w>c_bytes)return -1;
 if(original_bypass)return 1; /* Never re-encode Original */
 if(!lut)return -1;
 const size_t row_bytes=(size_t)w*3u;
 uint8_t *row=malloc(row_bytes);
 nx_preview_processor *preview=malloc(sizeof(*preview));
 if(!row||!preview||nx_preview_init(preview)!=0){
  free(row);free(preview);return -1;
 }
 nx_host_jpeg_writer *writer=nx_host_jpeg_writer_create_with_sampling(
                    dest,exif,exif_bytes,NX_HOST_JPEG_420);
 if(!writer){free(row);free(preview);return -1;}
 nx_bayer_rgb8_sink sink=nx_host_jpeg_writer_sink(writer);
 int bad=sink.begin(sink.user,w,h,1)!=0;
 for(unsigned yy=0;yy<h&&!bad;yy++){
  const uint8_t *yp=y+(size_t)yy*y_stride;
  const uint8_t *cp=c+(size_t)(yy/2u)*c_stride;
  for(unsigned x=0;x<w;x++){
   const unsigned pair=x&~1u;
   const unsigned cb=cp[pair+(order==NX_HOST420_CRCB_EXPERIMENTAL?1u:0u)];
   const unsigned cr=cp[pair+(order==NX_HOST420_CRCB_EXPERIMENTAL?0u:1u)];
   uint8_t pixel[3];
   decode_host(yp[x],cb,cr,model,pixel);
   nx_rgb12 input={preview->decode_srgb[pixel[0]],
                   preview->decode_srgb[pixel[1]],
                   preview->decode_srgb[pixel[2]],0},out;
   if(nx_lut_grid_host_apply(lut,grid,&input,&out,1)!=0){
    bad=1;break;
   }
   row[3u*x]=preview->encode_srgb[out.r>4095u?4095u:out.r];
   row[3u*x+1u]=preview->encode_srgb[out.g>4095u?4095u:out.g];
   row[3u*x+2u]=preview->encode_srgb[out.b>4095u?4095u:out.b];
  }
  if(!bad&&sink.write_row(sink.user,yy,row,row_bytes)!=0)bad=1;
 }
 if(!bad&&sink.commit(sink.user)!=0)bad=1;
 if(bad)sink.abort(sink.user);
 nx_host_jpeg_writer_destroy(writer);
 free(row);free(preview);
 return bad?-1:0;
}
int nx_host420_lutgrid_jpeg_from_reference(
    const uint8_t *y,size_t y_bytes,size_t y_stride,
    const uint8_t *c,size_t c_bytes,size_t c_stride,
    const uint8_t *rgb,size_t rgb_bytes,size_t rgb_stride,
    unsigned w,unsigned h,
    const nx_rgb12 *lut,unsigned grid,int original_bypass,
    const char *dest,const uint8_t *exif,size_t exif_bytes,
    nx_420_model_report *report){
 if(!report)return -1;
 const enum nx_420_model_verdict result=nx_420_multimodel_probe(
   y,y_bytes,y_stride,c,c_bytes,c_stride,
   rgb,rgb_bytes,rgb_stride,w,h,report);
 if(result!=NX_420_MODEL_DISTINCT||
    report->best_model<0||report->best_model>=NX_420_MODEL_COUNT||
    (report->best_order!=NX_420_ORDER_CBCR&&
     report->best_order!=NX_420_ORDER_CRCB))return -1;
 const enum nx_host420_order order=report->best_order==NX_420_ORDER_CBCR?
             NX_HOST420_CBCR_EXPERIMENTAL:NX_HOST420_CRCB_EXPERIMENTAL;
 return nx_host420_lutgrid_jpeg_hypothesis(
   y,y_bytes,y_stride,c,c_bytes,c_stride,w,h,
   order,report->best_model,lut,grid,original_bypass,dest,exif,exif_bytes);
}
