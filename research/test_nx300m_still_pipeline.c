#include "nx300m_still_pipeline.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static unsigned char pixels[800*480*3],original[800*480*3];
int main(void){
    for(unsigned i=0;i<sizeof(pixels);i++)pixels[i]=(unsigned char)(31u*i+13u);
    memcpy(original,pixels,sizeof(pixels));
    assert(nx_still_filter_inplace(0,NX_STILL_SRGB_RGB888,pixels,2400,800,480)==NX_STILL_BYPASSED);
    assert(memcmp(original,pixels,sizeof(pixels))==0);
    assert(nx_still_filter_inplace(106,NX_STILL_RAW_OR_UNKNOWN,pixels,2400,800,480)==NX_STILL_BYPASSED);
    assert(memcmp(original,pixels,sizeof(pixels))==0);
    assert(nx_still_filter_inplace(106,NX_STILL_SRGB_RGB888,pixels,2400,800,480)==NX_STILL_APPLIED);
    unsigned differences=0;
    for(unsigned i=0;i<sizeof(pixels);i++)if(pixels[i]!=original[i])differences++;
    assert(differences>sizeof(pixels)/10);
    assert(nx_still_filter_inplace(999,NX_STILL_SRGB_RGB888,pixels,2400,800,480)==NX_STILL_INVALID);
    memcpy(pixels,original,sizeof(pixels));
    for(unsigned i=0;i<sizeof(pixels);i+=3){
        pixels[i]=150;pixels[i+1]=90;pixels[i+2]=160;
    }
    assert(nx_still_filter_inplace(106,NX_STILL_JPEG_YCBCR444,pixels,2400,800,480)==NX_STILL_APPLIED);
    for(unsigned i=0;i<sizeof(pixels);i+=3){
        /* A monochrome look should make Cb and Cr close to neutral. */
        assert(pixels[i+1]>=124 && pixels[i+1]<=132);
        assert(pixels[i+2]>=124 && pixels[i+2]<=132);
    }
    assert(nx_still_filter_inplace(200,NX_STILL_JPEG_YCBCR444,pixels,1,800,480)==NX_STILL_INVALID);
    puts("PASS saved-still buffer FilmSim: JPEG/YCC444 and RGB effects; byte-exact RAW/Original bypass; invalid guards");
    return 0;
}
