#define _POSIX_C_SOURCE 200809L
/* Read-only host stress benchmark of the independent LUT65 -> JPEG path.
 * Synthetic sRGB888 pixels + an ephemeral authorized NX65 LUT on CI.
 * No native camera firmware, device, sensor RAW, serial identifiers or DMA.
 * Process high-water RSS is measured on Linux; host numbers are NOT camera.
 */
#include "nx300m_host_lutgrid_jpeg.h"
#include "nx300m_lut_grid_host.h"
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static const uint8_t exif_app1[]={
 'E','x','i','f',0,0,'I','I',42,0,8,0,0,0,0,0,0,0,0,0
};
static uint64_t fingerprint(const uint8_t *p,size_t n){
 uint64_t v=UINT64_C(14695981039346656037);
 for(size_t i=0;i<n;i++){v^=p[i];v*=UINT64_C(1099511628211);}
 return v;
}
static double sec(const struct timespec a,const struct timespec b){
 return (double)(b.tv_sec-a.tv_sec)+(double)(b.tv_nsec-a.tv_nsec)/1.0e9;
}
static int verify_jpeg(const char *path,size_t *size){
 struct stat st;
 if(lstat(path,&st)!=0||!S_ISREG(st.st_mode)||st.st_size<350)return -1;
 FILE *f=fopen(path,"rb");if(!f)return -1;
 int ok=0;
 uint8_t head[4],tail[2];
 if(fread(head,1,4,f)!=4)goto end;
 if(head[0]!=255||head[1]!=216||head[2]!=255||head[3]!=224)goto end;
 /* Exif APP1 must be a byte-for-byte copy, not merely a fake EXIF flag. */
 uint8_t window[sizeof(exif_app1)]={0};
 int found=0;
 for(unsigned i=0;i<4096;i++){
  int ch=fgetc(f);if(ch==EOF)break;
  memmove(window,window+1,sizeof(window)-1);
  window[sizeof(window)-1]=(uint8_t)ch;
  if(memcmp(window,exif_app1,sizeof(window))==0){found=1;break;}
 }
 if(!found||fseek(f,-2,SEEK_END)!=0||fread(tail,1,2,f)!=2)goto end;
 if(tail[0]!=255||tail[1]!=217)goto end;
 *size=(size_t)st.st_size;
 ok=1;
end:
 if(fclose(f)!=0)ok=0;
 return ok?0:-1;
}
static void fill_synthetic_rgb(uint8_t *out,size_t stride,unsigned w,unsigned h){
 for(unsigned y=0;y<h;y++){
  uint8_t *r=out+(size_t)y*stride;
  for(unsigned x=0;x<w;x++){
   r[x*3u]=(uint8_t)((x*11u+y*3u+13u)&255u);
   r[x*3u+1u]=(uint8_t)((x*2u+y*17u+71u)&255u);
   r[x*3u+2u]=(uint8_t)((x*7u+y*5u+(x>>5))&255u);
  }
  memset(r+(size_t)w*3u,0xa5u,stride-(size_t)w*3u);
 }
}
static int measure(unsigned w,unsigned h,unsigned repeats,
                   const char *lut_path,const char *outdir){
 const unsigned grid=65u;
 const size_t nodes=(size_t)grid*grid*grid;
 const size_t stride=(size_t)w*3u+16u;
 const size_t bytes=stride*h;
 if(!w||!h||w>8192||h>8192||bytes>64u*1024u*1024u)
  return 2;
 uint8_t *rgb=malloc(bytes);
 nx_rgb12 *lut=malloc(nodes*sizeof(*lut));
 if(!rgb||!lut){free(rgb);free(lut);return 2;}
 fill_synthetic_rgb(rgb,stride,w,h);
 if(nx_lut_grid_host_load(lut_path,grid,lut,nodes)!=0){
  fprintf(stderr,"REJECT: NX65 LUT load failed\n");
  free(rgb);free(lut);return 2;
 }
 const uint64_t old_source=fingerprint(rgb,bytes);
 const uint64_t old_lut=fingerprint((const uint8_t *)lut,nodes*sizeof(*lut));
 double durations[8]={0};
 size_t sizes[8]={0};
 for(unsigned r=0;r<repeats;r++){
  char out[1024];
  const int n=snprintf(out,sizeof(out),"%s/nx65_bench_%ld_%ux%u_%u.jpg",
                       outdir,(long)getpid(),w,h,r);
  if(n<0||(size_t)n>=sizeof(out)||access(out,F_OK)==0){
   free(rgb);free(lut);return 2;
  }
  struct timespec start,finish;
  if(clock_gettime(CLOCK_MONOTONIC,&start)!=0){
   free(rgb);free(lut);return 2;
  }
  const int status=nx_host_rgb888_lutgrid_jpeg(
    rgb,bytes,stride,w,h,lut,grid,0,out,exif_app1,sizeof(exif_app1));
  if(clock_gettime(CLOCK_MONOTONIC,&finish)!=0){
   free(rgb);free(lut);return 2;
  }
  if(status!=0||verify_jpeg(out,&sizes[r])!=0){
   fprintf(stderr,"REJECT: JPEG invalid or pixel pipeline failed\n");
   free(rgb);free(lut);return 1;
  }
  durations[r]=sec(start,finish);
  if(nx_host_rgb888_lutgrid_jpeg(
    rgb,bytes,stride,w,h,lut,grid,0,out,exif_app1,sizeof(exif_app1))!=-1){
   fprintf(stderr,"REJECT: create-only overwrite not blocked\n");
   free(rgb);free(lut);return 1;
  }
  if(unlink(out)!=0){free(rgb);free(lut);return 1;}
 }
 if(old_source!=fingerprint(rgb,bytes)||
    old_lut!=fingerprint((const uint8_t *)lut,nodes*sizeof(*lut))){
  fprintf(stderr,"REJECT: source or LUT changed\n");free(rgb);free(lut);return 1;
 }
 for(unsigned i=1;i<repeats;i++){
  double v=durations[i];unsigned k=i;
  while(k>0&&durations[k-1]>v){durations[k]=durations[k-1];k--;}
  durations[k]=v;
 }
 const unsigned idx=(95u*repeats+99u)/100u-1u;
 const double median=durations[repeats/2u];
 struct rusage ru;
 if(getrusage(RUSAGE_SELF,&ru)!=0){free(rgb);free(lut);return 2;}
 const uint64_t maxrss_kib=(uint64_t)ru.ru_maxrss;
 const double megapixels=(double)w*(double)h/1.0e6;
 printf("NX65_HOST_BENCH_JSON {"
   "\"host_only\":true,\"camera_fw114_verified\":false,"
   "\"source\":\"synthetic_RGB888_real_or_fixture_NX65_LUT\","
   "\"width\":%u,\"height\":%u,\"megapixels\":%.6f,"
   "\"repeat_count\":%u,\"seconds_min\":%.5f,"
   "\"seconds_median\":%.5f,\"seconds_p95\":%.5f,"
   "\"megapixels_per_sec_median\":%.4f,"
   "\"peak_process_rss_kib\":%" PRIu64 ","
   "\"input_copy_bytes\":%zu,\"nx65_lut_bytes\":%zu,"
   "\"jpeg_size_bytes\":%zu,"
   "\"source_immutable\":true,\"LUT_immutable\":true,"
   "\"exif_app1_preserved\":true,\"create_only\":true,"
   "\"destination_removed\":true}\n",
   w,h,megapixels,repeats,durations[0],median,durations[idx],
   median>0.0?megapixels/median:0.0,maxrss_kib,
   bytes,nodes*sizeof(*lut),sizes[0]);
 free(rgb);free(lut);
 return 0;
}
int main(int argc,char **argv){
 if(argc!=4){fprintf(stderr,"Usage: %s small|full NX65_LUT_PATH output_directory\n",argv[0]);return 2;}
 if(!strcmp(argv[1],"small"))return measure(1024u,768u,5u,argv[2],argv[3]);
 if(!strcmp(argv[1],"full"))return measure(5546u,3714u,1u,argv[2],argv[3]);
 fprintf(stderr,"Unknown test size (small or full)\n");return 2;
}
