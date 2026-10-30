#include "nx300m_host_ycc420_probe.h"
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* OFFLINE and strictly READ-ONLY. This tool does not access a camera.
 * Files must be COPIED Y/C + RGB8 reference from the exact same stage
 * (and crop) by a separately verified, nonintrusive procedure.
 * An original NX300M JPEG/SRW file cannot substitute for these plane dumps.
 */
static int unsigned_arg(const char *text,unsigned *value){
 char *end=NULL;
 errno=0;
 unsigned long result=strtoul(text,&end,10);
 if(errno||text==end||*end||result==0||result>65536u)return -1;
 *value=(unsigned)result;
 return 0;
}
static int read_file(const char *path,uint8_t **data,size_t *length){
 FILE *f=fopen(path,"rb");
 if(!f)return -1;
 if(fseek(f,0,SEEK_END)!=0){fclose(f);return -1;}
 long n=ftell(f);
 if(n<=0||n>268435456L||fseek(f,0,SEEK_SET)!=0){
  fclose(f);return -1;
 }
 *data=malloc((size_t)n);
 if(!*data){fclose(f);return -1;}
 const size_t actual=fread(*data,1,(size_t)n,f);
 const int close_rc=fclose(f);
 if(actual!=(size_t)n||close_rc!=0){
  free(*data);*data=NULL;return -1;
 }
 *length=(size_t)n;
 return 0;
}
int main(int argc,char **argv){
 if(argc!=9){
  fprintf(stderr,"Usage: %s width height y_stride c_stride rgb_stride Y.bin C.bin RGB888.bin\n",argv[0]);
  fprintf(stderr,"All inputs are read-only COPIES of the same-stage image. "
                 "Output is only a hypothesis, NOT NX300M native verification.\n");
  return 2;
 }
 unsigned width=0,height=0,ys=0,cs=0,rs=0;
 if(unsigned_arg(argv[1],&width)||unsigned_arg(argv[2],&height)||
    unsigned_arg(argv[3],&ys)||unsigned_arg(argv[4],&cs)||
    unsigned_arg(argv[5],&rs)){
  fputs("Invalid dimensions or strides\n",stderr);return 2;
 }
 uint8_t *data[3]={NULL,NULL,NULL};
 size_t lengths[3]={0,0,0};
 for(unsigned k=0;k<3;k++){
  if(read_file(argv[6+k],&data[k],&lengths[k])){
   fprintf(stderr,"Unable to read input file %u\n",k+1);
   for(unsigned j=0;j<3;j++)free(data[j]);
   return 2;
  }
 }
 nx_ycc420_evidence ev;
 nx_ycc420_assessment v=nx_host_ycc420_probe(
   data[0],lengths[0],ys,data[1],lengths[1],cs,
   data[2],lengths[2],rs,width,height,&ev);
 for(unsigned k=0;k<3;k++)free(data[k]);
 if(v==NX_YCC420_BAD_INPUT){
  fputs("REJECT: invalid or truncated copy / unsupported dimensions\n",stderr);
  return 2;
 }
 const char *label=v==NX_YCC420_CBCR?"CBCR_UNDER_BT601_HYPOTHESIS":
                   v==NX_YCC420_CRCB?"CRCB_UNDER_BT601_HYPOTHESIS":
                   "INCONCLUSIVE";
 printf("result=%s\nwidth=%u\nheight=%u\ninformative_pairs=%llu/%llu\n"
        "y_mae=%.3f\ncbcr_mae=%.3f\ncrcb_mae=%.3f\nscore_gap=%.3f\n",
        label,width,height,
        (unsigned long long)ev.informative_pairs,
        (unsigned long long)ev.chroma_pairs,
        ev.y_mae_milli/1000.0,
        ev.cbcr_mae_milli/1000.0,ev.crcb_mae_milli/1000.0,
        ev.winning_gap_milli/1000.0);
 puts("WARNING: This does not prove the actual NX300M 1.14 DMA packing, "
      "color range, camera buffer ownership, or JPEG encoder ABI.");
 return 0;
}
