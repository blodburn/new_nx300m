#include "nx300m_ycc420_multimodel_probe.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
enum {W=48,H=32,YS=56,CS=56,RS=W*3+7};
static uint8_t rgb[H][RS],y[H][YS],c[H/2][CS];
static uint8_t oldrgb[sizeof(rgb)],oldy[sizeof(y)],oldc[sizeof(c)];
static uint8_t cv(double v){
 long x=lround(v);return (uint8_t)(x<0?0:x>255?255:x);
}
static void encode(const uint8_t *p,unsigned model,uint8_t out[3]){
 const double kr=(model==1||model==3)?0.2126:0.299;
 const double kb=(model==1||model==3)?0.0722:0.114;
 double yy=kr*p[0]+(1.0-kr-kb)*p[1]+kb*p[2];
 double cb=128.0+(p[2]-yy)/(2.0*(1.0-kb));
 double cr=128.0+(p[0]-yy)/(2.0*(1.0-kr));
 if(model>=2){yy=16.0+yy*219.0/255.0;
   cb=128.0+(cb-128.0)*224.0/255.0;
   cr=128.0+(cr-128.0)*224.0/255.0;}
 out[0]=cv(yy);out[1]=cv(cb);out[2]=cv(cr);
}
static void prepare(unsigned model,unsigned order,int gray){
 static const uint8_t cols[][3]={
  {244,30,15},{10,48,250},{35,235,20},{253,130,15},
  {183,15,240},{13,231,236},{248,242,10},{33,15,180}};
 memset(rgb,0x5a,sizeof(rgb));
 memset(y,0xa5,sizeof(y));
 memset(c,0xc3,sizeof(c));
 for(unsigned row=0;row<H;row++)for(unsigned x=0;x<W;x++){
  const uint8_t *v=cols[((x/2u)+(row/2u)*7u)%8u];
  uint8_t *r=rgb[row]+3u*x;
  for(unsigned k=0;k<3;k++)r[k]=gray?128:v[k];
  uint8_t expected[3];encode(r,model,expected);
  y[row][x]=expected[0];
 }
 for(unsigned row=0;row<H;row+=2u)for(unsigned x=0;x<W;x+=2u){
  unsigned cb=0,cr=0;
  for(unsigned j=0;j<2;j++)for(unsigned i=0;i<2;i++){
   uint8_t expected[3];encode(rgb[row+j]+(x+i)*3u,model,expected);
   cb+=expected[1];cr+=expected[2];
  }
  c[row/2u][x+(order?1u:0u)]=(uint8_t)((cb+2u)/4u);
  c[row/2u][x+(order?0u:1u)]=(uint8_t)((cr+2u)/4u);
 }
 memcpy(oldrgb,rgb,sizeof(rgb));
 memcpy(oldy,y,sizeof(y));
 memcpy(oldc,c,sizeof(c));
}
static enum nx_420_model_verdict check(nx_420_model_report *r){
 return nx_420_multimodel_probe(&y[0][0],sizeof(y),YS,
   &c[0][0],sizeof(c),CS,&rgb[0][0],sizeof(rgb),RS,W,H,r);
}
int main(void){
 for(unsigned model=0;model<4;model++)for(unsigned order=0;order<2;order++){
  prepare(model,order,0);
  nx_420_model_report r;
  assert(check(&r)==NX_420_MODEL_DISTINCT);
  assert(r.best_model==(enum nx_420_model)model);
  assert(r.best_order==(enum nx_420_order)order);
  assert(r.sampled_pairs==W*H/4u);
  assert(r.best_gap_milli>=2500u);
  assert(r.informative_pairs>=8u);
  assert(!memcmp(y,oldy,sizeof(y)));
  assert(!memcmp(c,oldc,sizeof(c)));
  assert(!memcmp(rgb,oldrgb,sizeof(rgb)));
  assert(nx_420_model_name((enum nx_420_model)model)[0]=='B');
 }
 prepare(0,0,1);
 nx_420_model_report r;
 assert(check(&r)==NX_420_MODEL_INCONCLUSIVE);
 assert(r.informative_pairs==0u);
 prepare(0,0,0);
 memset(y,255,sizeof(y));
 assert(check(&r)==NX_420_MODEL_INCONCLUSIVE);
 prepare(0,0,0);
 memset(c,0,sizeof(c));
 assert(check(&r)==NX_420_MODEL_INCONCLUSIVE);
 prepare(0,0,0);
 assert(nx_420_multimodel_probe(&y[0][0],YS*(H-1u)+W-1u,YS,
   &c[0][0],sizeof(c),CS,&rgb[0][0],sizeof(rgb),RS,W,H,&r)
   ==NX_420_MODEL_INVALID);
 assert(nx_420_multimodel_probe(&y[0][0],sizeof(y),YS,
   &c[0][0],sizeof(c),CS,&rgb[0][0],sizeof(rgb),RS,W-1u,H,&r)
   ==NX_420_MODEL_INVALID);
 assert(nx_420_multimodel_probe(&y[0][0],sizeof(y),YS,
   &c[0][0],sizeof(c),CS,&rgb[0][0],sizeof(rgb),RS,W,H,NULL)
   ==NX_420_MODEL_INVALID);
 assert(!memcmp(rgb,oldrgb,sizeof(rgb)));
 puts("PASS 8 matrix/range/chroma-order copied-host hypotheses; 3 fail-closed ambiguity checks; truncated/odd/NULL guards; inputs unchanged");
 return 0;
}
