#define _POSIX_C_SOURCE 200809L
/* HOST-ONLY synthetic copied 4:2:0 -> real SpektraFilm LUT65 -> JPG.
 * The explicit BT.601/full CbCr hypothesis is an OFFLINE synthetic model.
 * DO NOT use these assumptions for NX300M 1.14 camera DMA or firmware.
 */
#include "nx300m_host420_lutgrid_jpeg.h"
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
enum { GRID=65 };
static const uint8_t app1[]={'E','x','i','f',0,0,'I','I',42,0,8,0,0,0,0,0,0,0,0,0};
static uint64_t fingerprint(const uint8_t *data,size_t n){
 uint64_t v=UINT64_C(14695981039346656037);
 for(size_t i=0;i<n;i++){v^=data[i];v*=UINT64_C(1099511628211);}
 return v;
}
static double elapsed(const struct timespec a,const struct timespec b){
 return (double)(b.tv_sec-a.tv_sec)+1.e-9*(double)(b.tv_nsec-a.tv_nsec);
}
static void fill(uint8_t *y,uint8_t *c,size_t y_stride,size_t c_stride,
                 unsigned w,unsigned h){
 for(unsigned j=0;j<h;j++){
  uint8_t *row=y+(size_t)j*y_stride;
  for(unsigned x=0;x<w;x++)
   row[x]=(uint8_t)(((x/8u)*13u+(j/4u)*17u)&255u);
  memset(row+w,0xa5,y_stride-w);
 }
 for(unsigned j=0;j<h/2u;j++){
  uint8_t *row=c+(size_t)j*c_stride;
  for(unsigned x=0;x<w;x+=2u){
   row[x]=(uint8_t)((100u+x/8u+j/4u)&255u);
   row[x+1u]=(uint8_t)((200u+x/4u+j/8u)&255u);
  }
  memset(row+w,0xc3,c_stride-w);
 }
}
static int check_jpeg(const char *path,size_t *output_bytes){
 struct stat st;
 if(lstat(path,&st)!=0||!S_ISREG(st.st_mode)||st.st_size<350)return -1;
 FILE *f=fopen(path,"rb");if(!f)return -1;
 uint8_t first[2],last[2],slide[sizeof(app1)]={0};
 int found=0,ok=0;
 if(fread(first,1,2,f)!=2||first[0]!=255||first[1]!=216)goto end;
 for(unsigned i=0;i<4096;i++){
  int ch=fgetc(f);if(ch==EOF)break;
  memmove(slide,slide+1,sizeof(slide)-1);
  slide[sizeof(slide)-1]=(uint8_t)ch;
  if(memcmp(slide,app1,sizeof(app1))==0){found=1;break;}
 }
 if(!found||fseek(f,-2,SEEK_END)!=0||fread(last,1,2,f)!=2)goto end;
 if(last[0]!=255||last[1]!=217)goto end;
 *output_bytes=(size_t)st.st_size;ok=1;
end:
 if(fclose(f)!=0)ok=0;
 return ok?0:-1;
}
static int run(unsigned w,unsigned h,unsigned repeats,
               const char *lutpath,const char *folder){
 const size_t ys=(size_t)w+16u,cs=(size_t)w+16u;
 const size_t ybytes=ys*h,cbytes=cs*(h/2u);
 if(w==0||h==0||(w&1u)||(h&1u)||w>8192||h>8192||repeats>8u||
    (uint64_t)w*h*3u>64u*1024u*1024u)return 2;
 uint8_t *y=malloc(ybytes),*c=malloc(cbytes);
 const size_t count=(size_t)GRID*GRID*GRID;
 nx_rgb12 *lut=malloc(count*sizeof(*lut));
 if(!y||!c||!lut){free(y);free(c);free(lut);return 2;}
 fill(y,c,ys,cs,w,h);
 if(nx_lut_grid_host_load(lutpath,GRID,lut,count)!=0){
  fprintf(stderr,"REJECT LUT65 load\n");free(y);free(c);free(lut);return 2;
 }
 const uint64_t hy=fingerprint(y,ybytes),hc=fingerprint(c,cbytes);
 const uint64_t hl=fingerprint((uint8_t *)lut,count*sizeof(*lut));
 double times[8]={0};size_t outputbytes=0;
 for(unsigned pass=0;pass<repeats;pass++){
  char path[1024];
  const int len=snprintf(path,sizeof(path),
           "%s/nx420_lut65_bench_%ld_%ux%u_%u.jpg",
           folder,(long)getpid(),w,h,pass);
  if(len<0||(size_t)len>=sizeof(path)||access(path,F_OK)==0){
   free(y);free(c);free(lut);return 2;
  }
  struct timespec a,b;
  if(clock_gettime(CLOCK_MONOTONIC,&a)!=0){free(y);free(c);free(lut);return 2;}
  int status=nx_host420_lutgrid_jpeg_hypothesis(
    y,ybytes,ys,c,cbytes,cs,w,h,
    NX_HOST420_CBCR_EXPERIMENTAL,NX_420_BT601_FULL,
    lut,GRID,0,path,app1,sizeof(app1));
  if(clock_gettime(CLOCK_MONOTONIC,&b)!=0){free(y);free(c);free(lut);return 2;}
  if(status!=0||check_jpeg(path,&outputbytes)!=0){
   fprintf(stderr,"REJECT stream420 JPEG output\n");
   free(y);free(c);free(lut);return 1;
  }
  times[pass]=elapsed(a,b);
  if(nx_host420_lutgrid_jpeg_hypothesis(
     y,ybytes,ys,c,cbytes,cs,w,h,
     NX_HOST420_CBCR_EXPERIMENTAL,NX_420_BT601_FULL,
     lut,GRID,0,path,app1,sizeof(app1))!=-1){
   fprintf(stderr,"REJECT overwrite rule\n");
   free(y);free(c);free(lut);return 1;
  }
  if(unlink(path)!=0){free(y);free(c);free(lut);return 1;}
 }
 if(fingerprint(y,ybytes)!=hy||fingerprint(c,cbytes)!=hc||
    fingerprint((uint8_t *)lut,count*sizeof(*lut))!=hl){
   fprintf(stderr,"REJECT input mutation\n");
   free(y);free(c);free(lut);return 1;
 }
 for(unsigned i=1;i<repeats;i++){
  double v=times[i];unsigned j=i;
  while(j>0&&times[j-1]>v){times[j]=times[j-1];j--;}
  times[j]=v;
 }
 struct rusage ru;
 if(getrusage(RUSAGE_SELF,&ru)!=0){free(y);free(c);free(lut);return 2;}
 const unsigned p95idx=(95u*repeats+99u)/100u-1u;
 printf("NX65_HOST420_BENCH_JSON {"
 "\"host_only\":true,\"camera_firmware_verified\":false,"
 "\"width\":%u,\"height\":%u,\"repeats\":%u,"
 "\"seconds_min\":%.5f,\"seconds_median\":%.5f,\"seconds_p95\":%.5f,"
 "\"peak_rss_kib\":%ld,\"y_plane_bytes\":%zu,\"chroma_plane_bytes\":%zu,"
 "\"nx65_lut_bytes\":%zu,\"jpeg_bytes\":%zu,"
 "\"inputs_unchanged\":true,\"exif_app1_preserved\":true,"
 "\"overwrite_blocked\":true,\"outputs_deleted\":true,"
 "\"order_and_model\":\"SYNTHETIC_BT601_FULL_CBCR_ONLY\"}\n",
 w,h,repeats,times[0],times[repeats/2u],times[p95idx],ru.ru_maxrss,
 ybytes,cbytes,count*sizeof(*lut),outputbytes);
 free(y);free(c);free(lut);
 return 0;
}
int main(int argc,char **argv){
 if(argc!=4){fprintf(stderr,"usage: %s small|full LUT65_PATH OUTDIR\n",argv[0]);return 2;}
 if(!strcmp(argv[1],"small"))return run(1024u,768u,5u,argv[2],argv[3]);
 if(!strcmp(argv[1],"full"))return run(5546u,3714u,1u,argv[2],argv[3]);
 return 2;
}
