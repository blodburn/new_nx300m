#define _POSIX_C_SOURCE 200809L
#include "nx300m_lut_grid_host.h"
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

enum { MIN_GRID=2,MAX_GRID=65,MAX_TEXT_BYTES=8*1024*1024 };
static unsigned clamp12(unsigned v){return v>4095u?4095u:v;}
static unsigned lerp12(unsigned a,unsigned b,unsigned fraction){
 uint64_t n=(uint64_t)a*(65536u-fraction)+(uint64_t)b*fraction+32768u;
 return (unsigned)(n>>16);
}
static void frac12(unsigned v,unsigned n,unsigned *lo,unsigned *hi,unsigned *q16){
 const unsigned long long scaled=(unsigned long long)clamp12(v)*(n-1u);
 *lo=(unsigned)(scaled/4095u);
 *hi=*lo+(*lo<n-1u);
 *q16=(unsigned)(((scaled%4095u)*65536u+2047u)/4095u);
}
int nx_lut_grid_host_apply(const nx_rgb12 *nodes,unsigned n,
                           const nx_rgb12 *src,nx_rgb12 *dst,size_t count){
 if(!nodes||!src||!dst||n<MIN_GRID||n>MAX_GRID)return -1;
 for(size_t i=0;i<count;i++){
  unsigned lows[3],highs[3],fracs[3];
  const unsigned rgb[3]={src[i].r,src[i].g,src[i].b};
  for(unsigned k=0;k<3;k++)
   frac12(rgb[k],n,&lows[k],&highs[k],&fracs[k]);
  nx_rgb12 result={0,0,0,0};
  uint16_t *out[3]={&result.r,&result.g,&result.b};
  for(unsigned ch=0;ch<3;ch++){
   unsigned q[2][2][2];
   for(unsigned b=0;b<2;b++)
    for(unsigned g=0;g<2;g++)
     for(unsigned r=0;r<2;r++){
      const size_t at=((size_t)(b?highs[2]:lows[2])*n+
                                (g?highs[1]:lows[1]))*n+
                                (r?highs[0]:lows[0]);
      const nx_rgb12 *p=&nodes[at];
      q[b][g][r]=clamp12(ch==0?p->r:ch==1?p->g:p->b);
     }
   unsigned x0=lerp12(lerp12(q[0][0][0],q[0][0][1],fracs[0]),
                       lerp12(q[0][1][0],q[0][1][1],fracs[0]),fracs[1]);
   unsigned x1=lerp12(lerp12(q[1][0][0],q[1][0][1],fracs[0]),
                       lerp12(q[1][1][0],q[1][1][1],fracs[0]),fracs[1]);
   *out[ch]=(uint16_t)lerp12(x0,x1,fracs[2]);
  }
  dst[i]=result;
 }
 return 0;
}
static int parse_channel(const char **ptr,unsigned *out){
 const unsigned char *p=(const unsigned char *)*ptr;
 while(*p==' '||*p=='\t')p++;
 if(*p<'0'||*p>'9')return -1;
 unsigned v=0;
 do {
  const unsigned d=(unsigned)(*p-'0');
  if(v>(4095u-d)/10u)return -1;
  v=10u*v+d;
  p++;
 }while(*p>='0'&&*p<='9');
 *ptr=(const char *)p;
 *out=v;
 return 0;
}
static int parse_row(const char *line,nx_rgb12 *dest){
 unsigned v[3]={0};
 const char *p=line;
 for(unsigned i=0;i<3;i++){
  if(parse_channel(&p,&v[i])!=0)return -1;
  if(i<2&&*p!=' '&&*p!='\t')return -1;
 }
 while(*p==' '||*p=='\t'||*p=='\n'||*p=='\r')p++;
 if(*p)return -1;
 dest->r=(uint16_t)v[0];dest->g=(uint16_t)v[1];
 dest->b=(uint16_t)v[2];dest->reserved=0;
 return 0;
}
int nx_lut_grid_host_load(const char *path,unsigned n,
                          nx_rgb12 *dst,size_t dst_nodes){
 if(!path||!path[0]||!dst||n<MIN_GRID||n>MAX_GRID)return -1;
 const size_t count=(size_t)n*n*n;
 if(dst_nodes<count)return -1;
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0)return -1;
 struct stat first,last;
 if(fstat(fd,&first)!=0||!S_ISREG(first.st_mode)||
    first.st_size<=0||first.st_size>MAX_TEXT_BYTES){
  close(fd);return -1;
 }
 FILE *f=fdopen(fd,"rb");
 if(!f){close(fd);return -1;}
 nx_rgb12 *stage=malloc(count*sizeof(*stage));
 if(!stage){fclose(f);return -1;}
 int ok=0;
 char line[128];
 if(!fgets(line,sizeof(line),f)||strcmp(line,"NX_LUT_RGB12_GRID_V1\n"))ok=-1;
 if(!ok){
  char expected[32];
  if(snprintf(expected,sizeof(expected),"grid=%u\n",n)<=0||
     !fgets(line,sizeof(line),f)||strcmp(line,expected))ok=-1;
 }
 for(size_t i=0;!ok&&i<count;i++){
  if(!fgets(line,sizeof(line),f)||!strchr(line,'\n')||
     parse_row(line,&stage[i])!=0)ok=-1;
 }
 if(!ok&&(fgetc(f)!=EOF||ferror(f)))ok=-1;
 if(fstat(fd,&last)!=0||
    first.st_dev!=last.st_dev||first.st_ino!=last.st_ino||
    first.st_size!=last.st_size||
    first.st_mtim.tv_sec!=last.st_mtim.tv_sec||
    first.st_mtim.tv_nsec!=last.st_mtim.tv_nsec||
    first.st_ctim.tv_sec!=last.st_ctim.tv_sec||
    first.st_ctim.tv_nsec!=last.st_ctim.tv_nsec)ok=-1;
 if(fclose(f)!=0)ok=-1;
 if(!ok)memcpy(dst,stage,count*sizeof(*stage));
 free(stage);
 return ok;
}
