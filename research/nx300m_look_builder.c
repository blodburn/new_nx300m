#include "nx300m_look_builder.h"
#include <math.h>
#include <string.h>

static float clip01(float x) { return x<0.f ? 0.f : (x>1.f ? 1.f : x); }
static unsigned short quant12(float x) {
    float y=clip01(x)*4095.f+0.5f;
    return (unsigned short)y;
}
static void mul3(const float a[9], const float x[3], float out[3]) {
    for(unsigned int k=0;k<3;k++)out[k]=a[3*k]*x[0]+a[3*k+1]*x[1]+a[3*k+2]*x[2];
}
void nx_look_params_identity(nx_look_params *p) {
    if(!p)return;
    memset(p,0,sizeof(*p));
    for(unsigned int c=0;c<3;c++) {
        p->sensor_to_reference[3*c+c]=1.f;
        p->film_color_matrix[3*c+c]=1.f;
    }
    p->saturation=1.f;p->gamma=1.f;
}
int nx_look_build_lut18(nx_rgb12 *dst,const nx_look_params *p) {
    if(!dst||!p||!isfinite(p->saturation)||p->saturation<0.f||p->saturation>3.f||
       !isfinite(p->gamma)||p->gamma<=0.f||p->gamma>5.f||
       !isfinite(p->shadow_gain)||!isfinite(p->highlight_gain)||
       p->shadow_gain < -1.f||p->shadow_gain>1.f||
       p->highlight_gain < -1.f||p->highlight_gain>1.f)return -1;
    for(unsigned int k=0;k<9;k++)
        if(!isfinite(p->sensor_to_reference[k])||!isfinite(p->film_color_matrix[k]))return -1;
    for(unsigned int k=0;k<3;k++)if(!isfinite(p->sensor_offset[k]))return -1;

    for(unsigned int blue=0;blue<NX_LUT_GRID;blue++)
        for(unsigned int green=0;green<NX_LUT_GRID;green++)
            for(unsigned int red=0;red<NX_LUT_GRID;red++) {
                float in[3]={(float)red/17.f,(float)green/17.f,(float)blue/17.f};
                float calibrated[3],filmed[3];
                mul3(p->sensor_to_reference,in,calibrated);
                for(unsigned int q=0;q<3;q++)calibrated[q]=clip01(calibrated[q]+p->sensor_offset[q]);
                mul3(p->film_color_matrix,calibrated,filmed);
                for(unsigned int q=0;q<3;q++)filmed[q]=clip01(filmed[q]);
                const float y=clip01(0.2126f*filmed[0]+0.7152f*filmed[1]+0.0722f*filmed[2]);
                const float sh=(1.f-y)*(1.f-y), hi=y*y;
                const float gain=1.f+p->shadow_gain*sh+p->highlight_gain*hi;
                unsigned int rgb[3]={0,0,0};
                for(unsigned int q=0;q<3;q++) {
                    float chroma=y+(filmed[q]-y)*p->saturation;
                    float toned=clip01(chroma*gain);
                    rgb[q]=quant12((p->gamma==1.f)?toned:powf(toned,p->gamma));
                }
                nx_rgb12 *node=&dst[(blue*NX_LUT_GRID+green)*NX_LUT_GRID+red];
                node->r=(uint16_t)rgb[0];node->g=(uint16_t)rgb[1];
                node->b=(uint16_t)rgb[2];node->reserved=0;
            }
    return 0;
}
