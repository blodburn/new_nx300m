#include "nx300m_lut18.h"
static uint16_t clamp12(unsigned int x){return (uint16_t)(x > 4095u ? 4095u : x);}
static unsigned int index3(unsigned int r,unsigned int g,unsigned int b){
    return (b*NX_LUT_GRID+g)*NX_LUT_GRID+r;
}
static uint16_t lerp(uint16_t a,uint16_t b,unsigned int tq16){
    uint64_t v=(uint64_t)a*(65536u-tq16)+(uint64_t)b*tq16+32768u;
    return (uint16_t)(v>>16);
}
static void grid_fraction(uint16_t c,unsigned int *lo,unsigned int *hi,unsigned int *fraction){
    unsigned int scaled=(unsigned int)clamp12(c)*(NX_LUT_GRID-1u);
    *lo=scaled/4095u;
    *hi=(*lo < NX_LUT_GRID-1u) ? *lo+1u : *lo;
    *fraction=((scaled%4095u)*65536u+2047u)/4095u;
}
static uint16_t component(const nx_rgb12 *v, int channel){
    return channel==0?v->r:(channel==1?v->g:v->b);
}
int nx_lut18_apply(const nx_rgb12 *lut,const nx_rgb12 *src,nx_rgb12 *dst,size_t pixels){
    if(!lut||!src||!dst)return -1;
    for(size_t p=0;p<pixels;++p){
        unsigned int r0,r1,g0,g1,b0,b1,fr,fg,fb;
        grid_fraction(src[p].r,&r0,&r1,&fr);
        grid_fraction(src[p].g,&g0,&g1,&fg);
        grid_fraction(src[p].b,&b0,&b1,&fb);
        unsigned int ir[2]={r0,r1},ig[2]={g0,g1},ib[2]={b0,b1};
        nx_rgb12 out={0,0,0,0};
        uint16_t *targets[3]={&out.r,&out.g,&out.b};
        for(int c=0;c<3;c++){
            uint16_t v[2][2][2];
            for(unsigned int bz=0;bz<2;bz++)
                for(unsigned int gy=0;gy<2;gy++)
                    for(unsigned int rx=0;rx<2;rx++)
                        v[bz][gy][rx]=clamp12(component(&lut[index3(ir[rx],ig[gy],ib[bz])],c));
            uint16_t m0=lerp(lerp(v[0][0][0],v[0][0][1],fr),lerp(v[0][1][0],v[0][1][1],fr),fg);
            uint16_t m1=lerp(lerp(v[1][0][0],v[1][0][1],fr),lerp(v[1][1][0],v[1][1][1],fr),fg);
            *targets[c]=lerp(m0,m1,fb);
        }
        dst[p]=out;
    }
    return 0;
}
void nx_lut18_identity(nx_rgb12 *lut){
    if(!lut)return;
    for(unsigned int b=0;b<NX_LUT_GRID;b++)
        for(unsigned int g=0;g<NX_LUT_GRID;g++)
            for(unsigned int r=0;r<NX_LUT_GRID;r++){
                nx_rgb12 *v=&lut[index3(r,g,b)];
                v->r=(uint16_t)((r*4095u+(NX_LUT_GRID-1u)/2u)/(NX_LUT_GRID-1u));
                v->g=(uint16_t)((g*4095u+(NX_LUT_GRID-1u)/2u)/(NX_LUT_GRID-1u));
                v->b=(uint16_t)((b*4095u+(NX_LUT_GRID-1u)/2u)/(NX_LUT_GRID-1u));
                v->reserved=0;
            }
}
