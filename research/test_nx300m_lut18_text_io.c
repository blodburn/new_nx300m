#define _POSIX_C_SOURCE 200809L
#include "nx300m_lut18_text_io.h"
#include "nx300m_preview_rgb.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static nx_rgb12 generated[NX_LUT_COUNT],loaded[NX_LUT_COUNT];
static unsigned char sentinel[sizeof(loaded)];
static void write_fixture(const char *path,int count,int corrupt,int extra){
 FILE *f=fopen(path,"wb");assert(f);
 assert(fputs("NX18_RGB12_TEXT_V1\n",f)>=0);
 for(int i=0;i<count;i++){
  nx_rgb12 x=generated[i];
  if(i==10&&corrupt)assert(fputs("4096 0 0\n",f)>=0);
  else assert(fprintf(f,"%u %u %u\n",x.r,x.g,x.b)>0);
 }
 if(extra)assert(fputs("0 0 0\n",f)>=0);
 assert(fclose(f)==0);
}
static void reset_and_reject(const char *path){
 memset(loaded,0xA5,sizeof(loaded));
 memcpy(sentinel,loaded,sizeof(loaded));
 assert(nx_lut18_text_load(path,loaded)!=0);
 assert(memcmp(loaded,sentinel,sizeof(loaded))==0);
}
int main(void){
 nx_lut18_identity(generated);
 char path[]="outputs/nx18-test-XXXXXX";
 int fd=mkstemp(path);assert(fd>=0);assert(close(fd)==0);
 write_fixture(path,NX_LUT_COUNT,0,0);
 memset(loaded,0,sizeof(loaded));
 assert(nx_lut18_text_load(path,loaded)==0);
 assert(memcmp(generated,loaded,sizeof(loaded))==0);
 nx_rgb12 src[2]={{0,0,0,0},{4095,4095,4095,0}},dst[2];
 assert(nx_lut18_apply(loaded,src,dst,2)==0);
 assert(dst[0].r==0&&dst[0].g==0&&dst[0].b==0);
 assert(dst[1].r==4095&&dst[1].g==4095&&dst[1].b==4095);
 nx_preview_processor preview;
 assert(nx_preview_init(&preview)==0);
 unsigned char rgb[3]={200,100,15},out[3]={0};
 assert(nx_preview_filter_rgb888(&preview,loaded,rgb,3,out,3,1,1)==0);
 for(unsigned k=0;k<3;k++)assert(abs((int)out[k]-(int)rgb[k])<=1);
 write_fixture(path,NX_LUT_COUNT-1,0,0);
 reset_and_reject(path);
 write_fixture(path,NX_LUT_COUNT,1,0);
 reset_and_reject(path);
 write_fixture(path,NX_LUT_COUNT,0,1);
 reset_and_reject(path);
 FILE *f=fopen(path,"wb");assert(f);
 assert(fputs("INVALID\n",f)>=0);
 assert(fclose(f)==0);
 reset_and_reject(path);
 write_fixture(path,NX_LUT_COUNT,0,0);
 char alias[]="outputs/nx18-alias-XXXXXX";
 fd=mkstemp(alias);assert(fd>=0);assert(close(fd)==0);
 assert(unlink(alias)==0);
 assert(symlink(path,alias)==0);
 reset_and_reject(alias);
 assert(unlink(alias)==0);
 assert(unlink(path)==0);
 reset_and_reject(path);
 assert(nx_lut18_text_load(NULL,loaded)!=0);
 assert(nx_lut18_text_load(path,NULL)!=0);
 puts("PASS NX18 text LUT import: 5832 nodes identity, RGB preview, malformed/truncated/extra/unsafe inputs, no partial publication");
 return 0;
}
