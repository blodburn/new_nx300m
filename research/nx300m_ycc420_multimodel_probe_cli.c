#define _POSIX_C_SOURCE 200809L
#include "nx300m_ycc420_multimodel_probe.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
enum { MAX_INPUT_BYTES=268435456 };
static int positive_uint(const char *s,unsigned *out){
 char *end=NULL;errno=0;
 unsigned long n=strtoul(s,&end,10);
 if(errno||s==end||*end||n==0||n>65536UL)return -1;
 *out=(unsigned)n;return 0;
}
static int read_regular(const char *path,unsigned char **buffer,size_t *length){
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0)return -1;
 struct stat st;
 if(fstat(fd,&st)!=0||!S_ISREG(st.st_mode)||st.st_size<=0||
    st.st_size>MAX_INPUT_BYTES){close(fd);return -1;}
 size_t size=(size_t)st.st_size;
 unsigned char *b=malloc(size);
 if(!b){close(fd);return -1;}
 size_t done=0;
 while(done<size){
  ssize_t n=read(fd,b+done,size-done);
  if(n<0&&errno==EINTR)continue;
  if(n<=0){free(b);close(fd);return -1;}
  done+=(size_t)n;
 }
 const int rc=close(fd);
 if(rc!=0){free(b);return -1;}
 *buffer=b;*length=size;
 return 0;
}
static void usage(const char *prog){
 fprintf(stderr,"Usage: %s WIDTH HEIGHT Y_STRIDE C_STRIDE RGB_STRIDE Y.bin C.bin RGB888.bin\n",prog);
 fputs("Inputs must be separately authorized, READ-ONLY SAME-STAGE COPIES with identical crop.\n"
       "Exit 0 distinct HOST HYPOTHESIS; 3 inconclusive; 2 invalid. Never camera DMA.\n",stderr);
}
int main(int argc,char **argv){
 if(argc==2&&!strcmp(argv[1],"--help")){usage(argv[0]);return 0;}
 if(argc!=9){usage(argv[0]);return 2;}
 unsigned w,h,ys,cs,rs;
 if(positive_uint(argv[1],&w)||positive_uint(argv[2],&h)||
    positive_uint(argv[3],&ys)||positive_uint(argv[4],&cs)||
    positive_uint(argv[5],&rs)){usage(argv[0]);return 2;}
 unsigned char *data[3]={NULL,NULL,NULL};
 size_t size[3]={0,0,0};
 for(unsigned i=0;i<3;i++)if(read_regular(argv[i+6],&data[i],&size[i])!=0){
  fprintf(stderr,"REJECT: copied input %u is missing, symlink, oversized, or unreadable\n",i+1);
  for(unsigned j=0;j<3;j++)free(data[j]);
  return 2;
 }
 nx_420_model_report report;
 const enum nx_420_model_verdict v=nx_420_multimodel_probe(
      data[0],size[0],ys,data[1],size[1],cs,
      data[2],size[2],rs,w,h,&report);
 for(unsigned i=0;i<3;i++)free(data[i]);
 if(v==NX_420_MODEL_INVALID){
  fputs("REJECT: unsupported metadata, truncated plane, or invalid stride\n",stderr);
  return 2;
 }
 printf("sampled_chroma_pairs=%" PRIu64 "\n",report.sampled_pairs);
 printf("informative_pairs=%" PRIu64 "\n",report.informative_pairs);
 for(unsigned m=0;m<NX_420_MODEL_COUNT;m++)
  for(unsigned o=0;o<2;o++){
   const nx_420_model_score *s=&report.candidates[m][o];
   printf("hypothesis=%s:%s y_mae=%.3f chroma_mae=%.3f combined=%.3f\n",
      nx_420_model_name((enum nx_420_model)m),o?"CrCb":"CbCr",
      s->y_mae_milli/1000.0,s->chroma_mae_milli/1000.0,
      s->combined_mae_milli/1000.0);
  }
 if(v==NX_420_MODEL_DISTINCT){
  printf("result=HOST_HYPOTHESIS_ONLY model=%s order=%s gap=%.3f\n",
    nx_420_model_name(report.best_model),
    report.best_order==NX_420_ORDER_CBCR?"CbCr":"CrCb",
    report.best_gap_milli/1000.0);
 }else{
  printf("result=INCONCLUSIVE gap=%.3f\n",report.best_gap_milli/1000.0);
 }
 puts("WARNING: Does NOT establish Samsung NX300M 1.14 DMA layout, actual matrix/range, capture ABI, or firmware safety.");
 return v==NX_420_MODEL_DISTINCT?0:3;
}
