#include "nx300m_preview_rgb.h"
#include <math.h>
#include <string.h>
#include <stdint.h>
int nx_preview_init(nx_preview_processor *p){
    if(!p)return -1;
    p->compare_original=0;
    for(unsigned i=0;i<256;i++){
        double x=(double)i/255.0;
        double linear=x<=.04045 ? x/12.92 : pow((x+.055)/1.055,2.4);
        p->decode_srgb[i]=(uint16_t)(linear*4095.0+0.5);
    }
    for(unsigned i=0;i<4096;i++){
        double x=(double)i/4095.0;
        double s=x<=.0031308 ? 12.92*x : 1.055*pow(x,1.0/2.4)-.055;
        if(s<0)s=0;
        if(s>1)s=1;
        p->encode_srgb[i]=(uint8_t)(s*255.0+0.5);
    }
    return 0;
}
int nx_preview_filter_rgb888(const nx_preview_processor *p,const nx_rgb12 *lut,
    const unsigned char *input,size_t input_stride,unsigned char *output,size_t output_stride,
    unsigned width,unsigned height){
    if(!p||!lut||!input||!output||!width||!height||width>16384||height>16384
       ||input_stride<(size_t)width*3||output_stride<(size_t)width*3)return -1;
    /* Staged output ensures no changes to source in copy mode and handles in-place if
       camera callback returns writable RGB888 output frame. */
    for(unsigned y=0;y<height;y++){
        const uint8_t *line=input+(size_t)y*input_stride;
        uint8_t *dest=output+(size_t)y*output_stride;
        if(p->compare_original){memmove(dest,line,(size_t)width*3);continue;}
        for(unsigned x=0;x<width;x++){
            const uint8_t *a=line+x*3;
            uint8_t *b=dest+x*3;
            nx_rgb12 in={p->decode_srgb[a[0]],p->decode_srgb[a[1]],
                         p->decode_srgb[a[2]],0},out;
            if(nx_lut18_apply(lut,&in,&out,1)!=0)return -1;
            b[0]=p->encode_srgb[out.r>4095?4095:out.r];
            b[1]=p->encode_srgb[out.g>4095?4095:out.g];
            b[2]=p->encode_srgb[out.b>4095?4095:out.b];
        }
    }
    return 0;
}
