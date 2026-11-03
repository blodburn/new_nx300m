#define _POSIX_C_SOURCE 200809L
#include "nx300m_host420_lutgrid_jpeg.h"
#include "nx300m_host_lutgrid_jpeg.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum {W=48,H=32,YS=56,CS=56,RS=W*3+7};
static uint8_t y[H][YS],c[H/2][CS],reference[H][RS],
               decoded[H][RS],original_y[sizeof(y)],
               original_c[sizeof(c)],original_ref[sizeof(reference)];
static const uint8_t exif[]={'E','x','i','f',0,0,'I','I',42,0,8,0,0,0,0,0,0,0,0,0};
static uint8_t u8(double v){long z=lround(v);return (uint8_t)(z<0?0:z>255?255:z);}
static void encode_ycc(const uint8_t *rgb,unsigned model,uint8_t out[3]){
 const double kr=(model==1u||model==3u)?0.2126:0.299;
 const double kb=(model==1u||model==3u)?0.0722:0.114;
 double lum=kr*rgb[0]+(1.-kr-kb)*rgb[1]+kb*rgb[2];
 double cb=128.+(rgb[2]-lum)/(2.*(1.-kb));
 double cr=128.+(rgb[0]-lum)/(2.*(1.-kr));
 if(model>=2u){lum=16.+lum*219./255.;cb=128.+(cb-128.)*224./255.;
                cr=128.+(cr-128.)*224./255.;}
 out[0]=u8(lum);out[1]=u8(cb);out[2]=u8(cr);
}
static uint8_t clip(int a){return (uint8_t)(a<0?0:a>255?255:a);}
static void decode_expected(unsigned l,unsigned cbb,unsigned crr,unsigned model,uint8_t *rgb){
 if(model!=0u){
  int limited=model>=2,bt709=(model==1u||model==3u);
  double yv=limited?((double)l-16.)*255./219.:(double)l;
  double s=limited?255./224.:1.;
  double cb=((int)cbb-128)*s,cr=((int)crr-128)*s;
  rgb[0]=clip((int)lround(yv+(bt709?1.5748:1.402)*cr));
  rgb[1]=clip((int)lround(yv-(bt709?0.187324:0.344136)*cb-
                                   (bt709?0.468124:0.714136)*cr));
  rgb[2]=clip((int)lround(yv+(bt709?1.8556:1.772)*cb));
 }else{
  int cb=(int)cbb-128,cr=(int)crr-128;
  rgb[0]=clip((int)l+((91881*cr+32768)>>16));
  rgb[1]=clip((int)l-((22554*cb+46802*cr+32768)>>16));
  rgb[2]=clip((int)l+((116130*cb+32768)>>16));
 }
}
static void fixture(unsigned model,unsigned swapped,int grayscale){
 static const uint8_t colors[][3]={
  {244,30,15},{10,48,250},{35,235,20},{253,130,15},
  {183,15,240},{13,231,236},{248,242,10},{33,15,180}
 };
 memset(y,0xA5,sizeof(y));memset(c,0xC3,sizeof(c));
 memset(reference,0x5A,sizeof(reference));memset(decoded,0x5A,sizeof(decoded));
 for(unsigned j=0;j<H;j++)for(unsigned i=0;i<W;i++){
  const uint8_t *value=colors[((i/2u)+(j/2u)*7u)%8u];
  uint8_t *p=reference[j]+3u*i;
  for(unsigned k=0;k<3;k++)p[k]=grayscale?128u:value[k];
  uint8_t data[3];encode_ycc(p,model,data);
  y[j][i]=data[0];
 }
 for(unsigned j=0;j<H;j+=2u)for(unsigned i=0;i<W;i+=2u){
  unsigned cb=0,cr=0;
  for(unsigned dy=0;dy<2;dy++)for(unsigned dx=0;dx<2;dx++){
   uint8_t encoded[3];
   encode_ycc(reference[j+dy]+3u*(i+dx),model,encoded);
   cb+=encoded[1];cr+=encoded[2];
  }
  c[j/2u][i+(swapped?1u:0u)]=(uint8_t)((cb+2u)/4u);
  c[j/2u][i+(swapped?0u:1u)]=(uint8_t)((cr+2u)/4u);
 }
 for(unsigned j=0;j<H;j++)for(unsigned i=0;i<W;i++){
  const unsigned pos=i&~1u;
  const unsigned cb=c[j/2u][pos+(swapped?1u:0u)];
  const unsigned cr=c[j/2u][pos+(swapped?0u:1u)];
  decode_expected(y[j][i],cb,cr,model,decoded[j]+3u*i);
 }
 memcpy(original_y,y,sizeof(y));memcpy(original_c,c,sizeof(c));
 memcpy(original_ref,reference,sizeof(reference));
}
static nx_rgb12 *make_lut(unsigned n,int inverse){
 const size_t count=(size_t)n*n*n;
 nx_rgb12 *result=malloc(count*sizeof(*result));assert(result);
 for(unsigned b=0;b<n;b++)for(unsigned g=0;g<n;g++)
 for(unsigned r=0;r<n;r++){
  nx_rgb12 *p=&result[((size_t)b*n+g)*n+r];
  unsigned vr=(r*4095u+(n-1u)/2u)/(n-1u);
  unsigned vg=(g*4095u+(n-1u)/2u)/(n-1u);
  unsigned vb=(b*4095u+(n-1u)/2u)/(n-1u);
  p->r=(uint16_t)(inverse?4095u-vr:vr);
  p->g=(uint16_t)(inverse?4095u-vg:vg);
  p->b=(uint16_t)(inverse?4095u-vb:vb);
  p->reserved=0;
 }
 return result;
}
static uint64_t read_jpg(const char *path,int *has_exif){
 FILE *f=fopen(path,"rb");assert(f);
 uint64_t hash=UINT64_C(14695981039346656037);
 uint8_t window[sizeof(exif)]={0};
 int first=-1,second=-1,prev=-1,last=-1;
 size_t total=0;*has_exif=0;
 for(int ch;(ch=fgetc(f))!=EOF;){
  if(total==0)first=ch;
  if(total==1)second=ch;
  memmove(window,window+1,sizeof(window)-1);
  window[sizeof(window)-1]=(uint8_t)ch;
  if(total+1>=sizeof(window)&&memcmp(window,exif,sizeof(exif))==0)*has_exif=1;
  prev=last;last=ch;
  hash^=(uint8_t)ch;hash*=UINT64_C(1099511628211);
  total++;
 }
 assert(!ferror(f)&&fclose(f)==0);
 assert(total>350&&first==255&&second==216&&prev==255&&last==217);
 return hash;
}
static void unchanged(void){
 assert(memcmp(original_y,y,sizeof(y))==0);
 assert(memcmp(original_c,c,sizeof(c))==0);
 assert(memcmp(original_ref,reference,sizeof(reference))==0);
}
int main(int argc,char **argv){
 if(argc!=1){(void)argv;return 2;}
 for(unsigned model=0;model<4;model++)for(unsigned swap=0;swap<2;swap++){
  fixture(model,swap,0);
  const unsigned n=model%2u?18u:65u;
  nx_rgb12 *lut=make_lut(n,swap);
  const size_t nbytes=(size_t)n*n*n*sizeof(*lut);
  nx_rgb12 *copy=malloc(nbytes);assert(copy);memcpy(copy,lut,nbytes);
  char stream[128],oracle[128];
  assert(snprintf(stream,sizeof(stream),"outputs/stream420_%ld_%u_%u.jpg",
                  (long)getpid(),model,swap)>0);
  assert(snprintf(oracle,sizeof(oracle),"outputs/stream420_ref_%ld_%u_%u.jpg",
                  (long)getpid(),model,swap)>0);
  assert(access(stream,F_OK)!=0&&access(oracle,F_OK)!=0);
  nx_420_model_report report;
  const int stream_code=nx_host420_lutgrid_jpeg_from_reference(
   &y[0][0],sizeof(y),YS,&c[0][0],sizeof(c),CS,
   &reference[0][0],sizeof(reference),RS,W,H,lut,n,0,
   stream,exif,sizeof(exif),&report);
  assert(stream_code==0&&report.verdict==NX_420_MODEL_DISTINCT);
  assert(report.best_model==(enum nx_420_model)model);
  assert(report.best_order==(enum nx_420_order)swap);
  assert(nx_host_rgb888_lutgrid_jpeg(
   &decoded[0][0],sizeof(decoded),RS,W,H,lut,n,0,oracle,
   exif,sizeof(exif))==0);
  int a=0,b=0;
  const uint64_t ha=read_jpg(stream,&a),hb=read_jpg(oracle,&b);
  assert(a&&b&&ha==hb); /* exact stream -> RGB -> JPEG parity */
  assert(nx_host420_lutgrid_jpeg_from_reference(
   &y[0][0],sizeof(y),YS,&c[0][0],sizeof(c),CS,
   &reference[0][0],sizeof(reference),RS,W,H,lut,n,0,
   stream,exif,sizeof(exif),&report)==-1); /* no overwrite */
  assert(read_jpg(stream,&a)==ha);
  unchanged();assert(memcmp(copy,lut,nbytes)==0);
  assert(unlink(stream)==0&&unlink(oracle)==0);
  free(copy);free(lut);
 }
 nx_rgb12 *lut=make_lut(65u,0);
 fixture(0,0,0);
 const char *missing="outputs/nx_stream420_never_publish.jpg";
 assert(access(missing,F_OK)!=0);
 assert(nx_host420_lutgrid_jpeg_hypothesis(
   &y[0][0],sizeof(y),YS,&c[0][0],sizeof(c),CS,W,H,
   NX_HOST420_CBCR_EXPERIMENTAL,NX_420_BT601_FULL,lut,65u,1,
   missing,NULL,0)==1);
 assert(nx_host420_lutgrid_jpeg_hypothesis(
   &y[0][0],sizeof(y)-YS,YS,&c[0][0],sizeof(c),CS,W,H,
   NX_HOST420_CBCR_EXPERIMENTAL,NX_420_BT601_FULL,lut,65u,0,
   missing,NULL,0)==-1);
 assert(nx_host420_lutgrid_jpeg_hypothesis(
   &y[0][0],sizeof(y),YS,&c[0][0],sizeof(c),CS,W,H,
   NX_HOST420_ORDER_UNSPECIFIED,NX_420_BT601_FULL,lut,65u,0,
   missing,NULL,0)==-1);
 assert(nx_host420_lutgrid_jpeg_hypothesis(
   &y[0][0],sizeof(y),YS,&c[0][0],sizeof(c),CS,W,H,
   NX_HOST420_CBCR_EXPERIMENTAL,(enum nx_420_model)42,lut,65u,0,
   missing,NULL,0)==-1);
 assert(nx_host420_lutgrid_jpeg_hypothesis(
   &y[0][0],sizeof(y),YS,&c[0][0],sizeof(c),CS,W-1u,H,
   NX_HOST420_CBCR_EXPERIMENTAL,NX_420_BT601_FULL,lut,65u,0,
   missing,NULL,0)==-1);
 fixture(0,0,1);
 nx_420_model_report inconclusive;
 assert(nx_host420_lutgrid_jpeg_from_reference(
   &y[0][0],sizeof(y),YS,&c[0][0],sizeof(c),CS,
   &reference[0][0],sizeof(reference),RS,W,H,lut,65u,0,
   missing,exif,sizeof(exif),&inconclusive)==-1);
 assert(inconclusive.verdict==NX_420_MODEL_INCONCLUSIVE);
 assert(access(missing,F_OK)!=0);
 unchanged();free(lut);
 puts("PASS 8 Y/C420 model+byte-order cases: NX65/NX18 streaming RGB/JPEG byte parity, guard, EXIF, no overwrite, no DMA");
 return 0;
}
