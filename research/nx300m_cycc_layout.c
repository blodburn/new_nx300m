#include "nx300m_cycc_layout.h"
#include <string.h>
#include <stdint.h>
_Static_assert(offsetof(nx_native_cycc,y0)==0x0c,"Y0 offset");
_Static_assert(offsetof(nx_native_cycc,y1)==0x10,"Y1 offset");
_Static_assert(offsetof(nx_native_cycc,c0)==0x14,"C0 offset");
_Static_assert(offsetof(nx_native_cycc,c1)==0x18,"C1 offset");
_Static_assert(offsetof(nx_native_cycc,scan_mode)==0x1c,"scan mode offset");
_Static_assert(offsetof(nx_native_cycc,image_ycc_type)==0x20,"image type offset");
int nx_cycc_make_contiguous(uint32_t base,uint32_t width,uint32_t height,
 uint32_t stride,uint32_t type,nx_native_cycc *out){
 if(!out||!base||width==0||height<2||width>19999||height>19999||
    stride<width||stride>19999)return -1;
 uint64_t plane=(uint64_t)stride*height;
 if((uint64_t)base+2u*plane>UINT32_MAX)return -1;
 nx_native_cycc h={width,height,stride,base,base+stride,
                  (uint32_t)(base+plane),(uint32_t)(base+plane+stride),1u,type};
 memcpy(out,&h,sizeof(h));return 0;
}
int nx_cycc_footprint(const nx_native_cycc *h,uint32_t *bytes,uint32_t *end_address){
 if(!h||!bytes||!end_address)return -1;
 nx_native_cycc v;
 if(nx_cycc_make_contiguous(h->y0,h->width,h->height,h->stride,h->image_ycc_type,&v)
    ||memcmp(h,&v,sizeof(v)))return -1;
 uint64_t total=2u*(uint64_t)h->stride*h->height;
 *bytes=(uint32_t)total;*end_address=(uint32_t)((uint64_t)h->y0+total);
 return 0;
}
int nx_cycc_read_contiguous_header(const void *data,size_t len,nx_native_cycc *out){
 if(!data||!out||len<sizeof(nx_native_cycc))return -1;
 nx_native_cycc v,w;
 memcpy(&v,data,sizeof(v));
 if(nx_cycc_make_contiguous(v.y0,v.width,v.height,v.stride,v.image_ycc_type,&w)
   ||memcmp(&v,&w,sizeof(v)))return -1;
 *out=v;return 0;
}
