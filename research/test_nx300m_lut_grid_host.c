#define _POSIX_C_SOURCE 200809L
#include "nx300m_lut_grid_host.h"
#include "nx300m_lut18.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static nx_rgb12 *nodes(unsigned n){
 size_t count=(size_t)n*n*n;
 nx_rgb12 *p=malloc(count*sizeof(*p));assert(p);
 for(unsigned b=0;b<n;b++)for(unsigned g=0;g<n;g++)
 for(unsigned r=0;r<n;r++){
  nx_rgb12 *v=&p[((size_t)b*n+g)*n+r];
  v->r=(uint16_t)((r*4095u+(n-1u)/2u)/(n-1u));
  v->g=(uint16_t)((g*4095u+(n-1u)/2u)/(n-1u));
  v->b=(uint16_t)((b*4095u+(n-1u)/2u)/(n-1u));
  v->reserved=0;
 }
 return p;
}
static void write_fixture(const char *path,unsigned n,const nx_rgb12 *src,
                          size_t count,int bad_line,int extra){
 FILE *f=fopen(path,"wb");assert(f);
 assert(fputs("NX_LUT_RGB12_GRID_V1\n",f)>=0);
 assert(fprintf(f,"grid=%u\n",n)>0);
 for(size_t i=0;i<count;i++){
  if(i==10&&bad_line)assert(fputs("9999 0 0\n",f)>=0);
  else assert(fprintf(f,"%u %u %u\n",src[i].r,src[i].g,src[i].b)>0);
 }
 if(extra)assert(fputs("0 0 0\n",f)>=0);
 assert(fclose(f)==0);
}
static void reject_and_unchanged(const char *path,unsigned n,nx_rgb12 *dest,
                                  size_t count){
 memset(dest,0xA5,count*sizeof(*dest));
 nx_rgb12 *original=malloc(count*sizeof(*dest));assert(original);
 memcpy(original,dest,count*sizeof(*dest));
 assert(nx_lut_grid_host_load(path,n,dest,count)==-1);
 assert(memcmp(dest,original,count*sizeof(*dest))==0);
 free(original);
}
int main(int argc,char **argv){
 if(argc==3){
  unsigned n=0;
  assert(sscanf(argv[1],"%u",&n)==1&&n>=2&&n<=65);
  size_t count=(size_t)n*n*n;
  nx_rgb12 *lut=malloc(count*sizeof(*lut));assert(lut);
  assert(nx_lut_grid_host_load(argv[2],n,lut,count)==0);
  nx_rgb12 src[3]={{123,456,789,0},{2048,3030,1024,0},{4095,4095,4095,0}},dst[3];
  assert(nx_lut_grid_host_apply(lut,n,src,dst,3)==0);
  for(unsigned i=0;i<3;i++){
   assert(dst[i].r<=4095&&dst[i].g<=4095&&dst[i].b<=4095);
   assert(dst[i].reserved==0);
  }
  free(lut);
  puts("PASS ephemeral external host RGB12 LUT loaded/applied; no camera storage or firmware use");
  return 0;
 }
 assert(argc==1);
 for(unsigned n=18;n<=65;n+=47){
  size_t count=(size_t)n*n*n;
  nx_rgb12 *reference=nodes(n);
  nx_rgb12 *loaded=malloc(count*sizeof(*loaded));assert(loaded);
  char path[]="outputs/nx-grid-host-XXXXXX";
  int fd=mkstemp(path);assert(fd>=0);assert(close(fd)==0);
  write_fixture(path,n,reference,count,0,0);
  assert(nx_lut_grid_host_load(path,n,loaded,count)==0);
  assert(memcmp(reference,loaded,count*sizeof(*loaded))==0);
  nx_rgb12 inputs[6]={{0,0,0,0},{100,1000,2000,0},{2048,4095,17,0},
     {4095,4095,4095,0},{4095,0,2048,0},{2,4,8,0}},outputs[6];
  assert(nx_lut_grid_host_apply(loaded,n,inputs,outputs,6)==0);
  for(unsigned i=0;i<6;i++){
   assert(abs((int)outputs[i].r-(int)inputs[i].r)<=4);
   assert(abs((int)outputs[i].g-(int)inputs[i].g)<=4);
   assert(abs((int)outputs[i].b-(int)inputs[i].b)<=4);
  }
  if(n==18){
   nx_rgb12 original[6];
   assert(nx_lut18_apply(loaded,inputs,original,6)==0);
   assert(memcmp(original,outputs,sizeof(original))==0);
  }
  write_fixture(path,n,reference,count-1,0,0);reject_and_unchanged(path,n,loaded,count);
  write_fixture(path,n,reference,count,1,0);reject_and_unchanged(path,n,loaded,count);
  write_fixture(path,n,reference,count,0,1);reject_and_unchanged(path,n,loaded,count);
  write_fixture(path,n,reference,count,0,0);
  char alias[]="outputs/nx-grid-symlink-XXXXXX";
  fd=mkstemp(alias);assert(fd>=0);assert(close(fd)==0);
  assert(unlink(alias)==0&&symlink(path,alias)==0);
  reject_and_unchanged(alias,n,loaded,count);
  assert(unlink(alias)==0);
  assert(nx_lut_grid_host_load(path,n,loaded,count-1)==-1);
  assert(unlink(path)==0);
  free(reference);free(loaded);
 }
 puts("PASS host LUT grid 18 and 65: fixed interpolation parity, 2.1MiB LUT memory, identity, malformed and symlink fail-closed");
 return 0;
}
