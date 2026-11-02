#define _POSIX_C_SOURCE 200809L
#include "nx300m_host_420_film_jpeg.h"
#include "nx300m_ycc420_multimodel_probe.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
enum {W=48,H=32,YS=56,CS=56,RS=W*3+7};
static uint8_t rgb[H][RS],y[H][YS],c[H/2][CS];
static uint8_t original_rgb[sizeof(rgb)],original_y[sizeof(y)],
               original_c[sizeof(c)];
static uint8_t u8(double v){
 long n=lround(v);return (uint8_t)(n<0?0:n>255?255:n);
}
static void encode(const uint8_t *p,unsigned model,uint8_t out[3]){
 const double kr=(model==1u||model==3u)?0.2126:0.299;
 const double kb=(model==1u||model==3u)?0.0722:0.114;
 double yy=kr*p[0]+(1.0-kr-kb)*p[1]+kb*p[2];
 double cb=128.0+(p[2]-yy)/(2.0*(1.0-kb));
 double cr=128.0+(p[0]-yy)/(2.0*(1.0-kr));
 if(model>=2u){yy=16.+yy*219./255.;
   cb=128.+(cb-128.)*224./255.;
   cr=128.+(cr-128.)*224./255.;}
 out[0]=u8(yy);out[1]=u8(cb);out[2]=u8(cr);
}
static void make(unsigned model,unsigned order,int gray){
 static const uint8_t colors[][3]={
  {244,30,15},{10,48,250},{35,235,20},{253,130,15},
  {183,15,240},{13,231,236},{248,242,10},{33,15,180}
 };
 memset(rgb,0x5a,sizeof(rgb));memset(y,0xa5,sizeof(y));
 memset(c,0xc3,sizeof(c));
 for(unsigned row=0;row<H;row++)for(unsigned x=0;x<W;x++){
  const uint8_t *v=colors[((x/2u)+(row/2u)*7u)%8u];
  uint8_t *r=rgb[row]+3u*x;
  for(unsigned k=0;k<3;k++)r[k]=gray?128u:v[k];
  uint8_t encoded[3];encode(r,model,encoded);
  y[row][x]=encoded[0];
 }
 for(unsigned row=0;row<H;row+=2u)for(unsigned x=0;x<W;x+=2u){
  unsigned cb=0,cr=0;
  for(unsigned j=0;j<2;j++)for(unsigned i=0;i<2;i++){
   uint8_t e[3];encode(rgb[row+j]+(x+i)*3u,model,e);
   cb+=e[1];cr+=e[2];
  }
  c[row/2u][x+(order?1u:0u)]=(uint8_t)((cb+2u)/4u);
  c[row/2u][x+(order?0u:1u)]=(uint8_t)((cr+2u)/4u);
 }
 memcpy(original_rgb,rgb,sizeof(rgb));
 memcpy(original_y,y,sizeof(y));
 memcpy(original_c,c,sizeof(c));
}
static int apply(const char *path,unsigned film,nx_420_model_report *report){
 return nx_host420_film_to_jpeg_from_reference(
  &y[0][0],sizeof(y),YS,&c[0][0],sizeof(c),CS,
  &rgb[0][0],sizeof(rgb),RS,W,H,film,path,NULL,0,report);
}
static void unchanged(void){
 assert(!memcmp(original_y,y,sizeof(y)));
 assert(!memcmp(original_c,c,sizeof(c)));
 assert(!memcmp(original_rgb,rgb,sizeof(rgb)));
}
int main(void){
 for(unsigned m=0;m<4;m++)for(unsigned order=0;order<2;order++){
  make(m,order,0);
  char path[128];
  assert(snprintf(path,sizeof(path),
    "outputs/nx_model_gate_%ld_%u_%u.jpg",
    (long)getpid(),m,order)>0);
  assert(access(path,F_OK)!=0);
  nx_420_model_report report;
  assert(apply(path,101,&report)==0);
  assert(report.verdict==NX_420_MODEL_DISTINCT);
  assert(report.best_model==(enum nx_420_model)m);
  assert(report.best_order==(enum nx_420_order)order);
  FILE *f=fopen(path,"rb");assert(f);
  assert(fgetc(f)==255&&fgetc(f)==216);
  assert(fclose(f)==0);
  assert(apply(path,101,&report)==-1); /* never overwrite */
  unchanged();
  assert(unlink(path)==0);
 }
 make(0,0,1);
 const char *no_out="outputs/nx_model_gate_gray_refuse.jpg";
 nx_420_model_report report;
 assert(access(no_out,F_OK)!=0);
 assert(apply(no_out,101,&report)==-1);
 assert(report.verdict==NX_420_MODEL_INCONCLUSIVE);
 assert(access(no_out,F_OK)!=0);
 unchanged();
 make(1,1,0);
 const char *original_out="outputs/nx_model_gate_original_noop.jpg";
 assert(access(original_out,F_OK)!=0);
 assert(apply(original_out,0,&report)==1);
 assert(access(original_out,F_OK)!=0);
 assert(nx_host420_film_to_jpeg_from_reference(
   &y[0][0],sizeof(y),YS,&c[0][0],sizeof(c),CS,
   &rgb[0][0],(H-1u)*RS+W*3u-1u,RS,W,H,101,
   original_out,NULL,0,&report)==-1);
 assert(access(original_out,F_OK)!=0);
 assert(nx_host420_film_to_jpeg_from_reference(
   &y[0][0],sizeof(y),YS,&c[0][0],sizeof(c),CS,
   &rgb[0][0],sizeof(rgb),RS,W,H,101,
   original_out,NULL,0,NULL)==-1);
 unchanged();
 puts("PASS all 8 420 color-model+chroma-order hypotheses gate host JPEG; inconclusive and invalid rejected; Original bypass; inputs unchanged");
 return 0;
}
