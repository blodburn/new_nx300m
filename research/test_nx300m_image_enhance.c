#include "nx300m_image_enhance.h"
#include "nx300m_still_enhanced.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <stdint.h>
enum {W=48,H=32,STRIDE=W*3+7,BYTES=STRIDE*H};
static unsigned char pixels[BYTES],backup[BYTES];
static void make_image(void){
    for(unsigned y=0;y<H;y++){
        for(unsigned x=0;x<W;x++){
            size_t i=(size_t)y*STRIDE+x*3u;
            int tone=(x<W/2)?55:195;
            /* Alternating chroma but equal local light: fabricated noisy wall. */
            pixels[i]=(uint8_t)(tone+(x%3==0?13:-9));
            pixels[i+1]=(uint8_t)(tone+(y%3==0?2:-2));
            pixels[i+2]=(uint8_t)(tone+(x%2?12:-11));
        }
        memset(pixels+(size_t)y*STRIDE+W*3,0xCD,STRIDE-W*3);
    }
    memcpy(backup,pixels,sizeof(pixels));
}
static int avg_noise(const unsigned char *p,unsigned xa,unsigned xb){
    unsigned n=0;int err=0;
    for(unsigned y=4;y<H-4;y++)
        for(unsigned x=xa;x<xb;x++){
            const unsigned char *a=p+(size_t)y*STRIDE+3*x;
            /* compare magnitude of R-B color deviation in flat patches */
            err+=abs((int)a[0]-(int)a[2]);n++;
        }
    return err/(int)n;
}
int main(void){
    make_image();
    int before=avg_noise(pixels,4,18);
    assert(nx_image_enhance_rgb888(pixels,STRIDE,W,H)==0);
    /* Streaming row API must be bit-exact with the existing full-frame
     * algorithm, including top/bottom border behavior and row padding. */
    unsigned char row_output[W*3u];
    for(unsigned y=0;y<H;y++){
        const unsigned char *prev=y?backup+(size_t)(y-1)*STRIDE:NULL;
        const unsigned char *cur=backup+(size_t)y*STRIDE;
        const unsigned char *next=y+1<H?backup+(size_t)(y+1)*STRIDE:NULL;
        assert(nx_image_enhance_rgb888_row(prev,cur,next,row_output,W,y,H)==0);
        assert(memcmp(row_output,pixels+(size_t)y*STRIDE,W*3u)==0);
    }
    assert(nx_image_enhance_rgb888_row(NULL,NULL,NULL,row_output,W,0,H)==-1);
    assert(nx_image_enhance_rgb888_row(NULL,backup,NULL,row_output,W,1,H)==-1);
    int after=avg_noise(pixels,4,18);
    assert(after<before);
    for(unsigned y=0;y<H;y++)
        for(unsigned x=3*W;x<STRIDE;x++)
            assert(pixels[(size_t)y*STRIDE+x]==0xCD);
    /* A sharp 55→195 edge should stay separated even after smoothing. */
    const unsigned char *a=pixels+(size_t)H/2*STRIDE;
    int left=a[(W/2-1)*3],right=a[(W/2)*3];
    assert(right-left>90);
    unsigned char uniform[3*6*4];
    memset(uniform,128,sizeof(uniform));
    assert(nx_image_enhance_rgb888(uniform,6*3,6,4)==0);
    for(size_t i=0;i<sizeof(uniform);i++)assert(uniform[i]==128);
    assert(nx_image_enhance_rgb888(NULL,STRIDE,W,H)==-1);
    assert(nx_image_enhance_rgb888(pixels,2,W,H)==-1);
    assert(nx_image_enhance_rgb888(pixels,STRIDE,0,H)==-1);
    assert(nx_image_enhance_rgb888(pixels,STRIDE,20000,H)==-1);
    make_image();
    assert(nx_still_filter_enhanced_inplace(106,NX_STILL_RAW_OR_UNKNOWN,
               pixels,STRIDE,W,H)==NX_STILL_BYPASSED);
    assert(memcmp(pixels,backup,BYTES)==0);
    assert(nx_still_filter_enhanced_inplace(0,NX_STILL_SRGB_RGB888,
               pixels,STRIDE,W,H)==NX_STILL_BYPASSED);
    assert(memcmp(pixels,backup,BYTES)==0);
    assert(nx_still_filter_enhanced_inplace(106,NX_STILL_JPEG_YCBCR444,
               pixels,STRIDE,W,H)==NX_STILL_BYPASSED);
    assert(memcmp(pixels,backup,BYTES)==0);
    assert(nx_still_filter_enhanced_inplace(999,NX_STILL_SRGB_RGB888,
               pixels,STRIDE,W,H)==NX_STILL_INVALID);
    assert(memcmp(pixels,backup,BYTES)==0);
    assert(nx_still_filter_enhanced_inplace(103,NX_STILL_SRGB_RGB888,
               pixels,STRIDE,W,H)==NX_STILL_APPLIED);
    assert(memcmp(pixels,backup,BYTES)!=0);
    for(unsigned y=0;y<H;y++)
        for(unsigned x=3*W;x<STRIDE;x++)
            assert(pixels[(size_t)y*STRIDE+x]==0xCD);
    puts("PASS opt-in JPEG RGB quality: edge-aware noise reduction, neutral/edge/padding fidelity, full-frame staging, RAW/Original/unknown exact bypass");
    return 0;
}
