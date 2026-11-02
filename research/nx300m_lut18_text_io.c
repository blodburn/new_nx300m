#define _POSIX_C_SOURCE 200809L
#include "nx300m_lut18_text_io.h"
#include <ctype.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define MAX_TEXT_BYTES (256u*1024u)

static int read_channel(const char **at,unsigned *value){
 const unsigned char *p=(const unsigned char *)*at;
 while(*p==' '||*p=='\t')p++;
 if(!(*p>='0'&&*p<='9'))return -1;
 unsigned v=0;
 do {
  unsigned digit=(unsigned)(*p-'0');
  if(v>(4095u-digit)/10u)return -1;
  v=10u*v+digit;
  p++;
 }while(*p>='0'&&*p<='9');
 *at=(const char *)p;
 *value=v;
 return 0;
}
static int parse_row(const char *line,nx_rgb12 *out){
 const char *p=line;
 unsigned v[3];
 for(unsigned i=0;i<3;i++){
  if(read_channel(&p,&v[i])!=0)return -1;
  if(i<2&&*p!=' '&&*p!='\t')return -1;
 }
 while(*p==' '||*p=='\t'||*p=='\r'||*p=='\n')p++;
 if(*p)return -1;
 out->r=(uint16_t)v[0];out->g=(uint16_t)v[1];
 out->b=(uint16_t)v[2];out->reserved=0;
 return 0;
}
int nx_lut18_text_load(const char *path,nx_rgb12 *dst){
 if(!path||!path[0]||!dst)return -1;
 const int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0)return -1;
 struct stat before,after;
 if(fstat(fd,&before)!=0||!S_ISREG(before.st_mode)||
    before.st_size<=0||before.st_size>MAX_TEXT_BYTES){
  close(fd);return -1;
 }
 FILE *f=fdopen(fd,"rb");
 if(!f){close(fd);return -1;}
 nx_rgb12 *stage=malloc(sizeof(nx_rgb12)*NX_LUT_COUNT);
 if(!stage){fclose(f);return -1;}
 char line[128]={0};
 int ok=0;
 if(!fgets(line,sizeof(line),f)||
    (strcmp(line,"NX18_RGB12_TEXT_V1\n")!=0&&
     strcmp(line,"NX18_RGB12_TEXT_V1\r\n")!=0))ok=-1;
 for(unsigned i=0;ok==0&&i<NX_LUT_COUNT;i++){
  if(!fgets(line,sizeof(line),f) || !strchr(line,'\n') ||
     parse_row(line,&stage[i])!=0)ok=-1;
 }
 if(ok==0&&(fgetc(f)!=EOF||ferror(f)))ok=-1;
 if(fstat(fd,&after)!=0||
    before.st_dev!=after.st_dev||before.st_ino!=after.st_ino||
    before.st_size!=after.st_size||before.st_mtime!=after.st_mtime||
    before.st_ctime!=after.st_ctime)ok=-1;
 if(fclose(f)!=0)ok=-1;
 if(ok==0)memcpy(dst,stage,sizeof(nx_rgb12)*NX_LUT_COUNT);
 free(stage);
 return ok;
}
