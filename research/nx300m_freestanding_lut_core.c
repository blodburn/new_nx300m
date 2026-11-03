#include "nx300m_freestanding_lut_core.h"
/* 32-bit-only fixed point math. Bounds:
 * scaled <= 4095*64 = 262080;
 * (scaled % 4095)*65536+2047 < 2^32;
 * lerp <= 4095*65536+32768 < 2^32.
 * No 64-bit division, software FP, compiler runtime or libc dependency.
 */
static unsigned clamp12(unsigned x){return x>4095u?4095u:x;}
static unsigned lerp12(unsigned a,unsigned b,unsigned q){
 unsigned v=a*(65536u-q)+b*q+32768u;
 return v>>16;
}
static void frac12(unsigned v,unsigned n,
                   unsigned *lo,unsigned *hi,unsigned *q16){
 const unsigned scaled=clamp12(v)*(n-1u);
 *lo=scaled/4095u;
 *hi=*lo+(*lo<n-1u);
 *q16=((scaled%4095u)*65536u+2047u)/4095u;
}
int nx_film_core_apply_rgb12(const nx_rgb12 *nodes,size_t nodes_available,
                             unsigned n,const nx_rgb12 *src,
                             nx_rgb12 *dst,size_t count){
 if(!nodes||!src||!dst||n<2u||n>65u||
    nodes_available<(size_t)n*n*n)return -1;
 for(size_t i=0;i<count;i++){
  unsigned lows[3],highs[3],fracs[3];
  const unsigned rgb[3]={src[i].r,src[i].g,src[i].b};
  for(unsigned k=0;k<3u;k++)
   frac12(rgb[k],n,&lows[k],&highs[k],&fracs[k]);
  nx_rgb12 result={0u,0u,0u,0u};
  uint16_t *out[3]={&result.r,&result.g,&result.b};
  for(unsigned ch=0;ch<3u;ch++){
   unsigned q[2][2][2];
   for(unsigned b=0;b<2u;b++)
    for(unsigned g=0;g<2u;g++)
     for(unsigned r=0;r<2u;r++){
      const size_t at=((size_t)(b?highs[2]:lows[2])*n+
                                (g?highs[1]:lows[1]))*n+
                                (r?highs[0]:lows[0]);
      const nx_rgb12 *p=&nodes[at];
      q[b][g][r]=clamp12(ch==0u?p->r:ch==1u?p->g:p->b);
     }
   const unsigned x0=lerp12(lerp12(q[0][0][0],q[0][0][1],fracs[0]),
                             lerp12(q[0][1][0],q[0][1][1],fracs[0]),fracs[1]);
   const unsigned x1=lerp12(lerp12(q[1][0][0],q[1][0][1],fracs[0]),
                             lerp12(q[1][1][0],q[1][1][1],fracs[0]),fracs[1]);
   *out[ch]=(uint16_t)lerp12(x0,x1,fracs[2]);
  }
  dst[i]=result;
 }
 return 0;
}
