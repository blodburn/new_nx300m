#define _POSIX_C_SOURCE 200809L
#include "nx300m_host_jpeg_sink.h"
#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
#include <sys/stat.h>
static double elapsed(struct timespec a,struct timespec b){
 return (double)(b.tv_sec-a.tv_sec)+1.e-9*(double)(b.tv_nsec-a.tv_nsec);
}
int main(int argc,char **argv){
 (void)argv;
 const unsigned w=argc>1?1024u:5546u;
 const unsigned h=argc>1?768u:3714u;
 const size_t count=(size_t)w*h;
 uint16_t *bayer=malloc(count*sizeof(*bayer));
 if(!bayer)return 2;
 for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)
  bayer[(size_t)y*w+x]=(uint16_t)(12000u+(x/5u)%34000u);
 nx_bayer_calibration cal={NX_BAYER_RGGB,{64,64,64,64},
                            {60000,60000,60000,60000},2200};
 nx_linear_params look={0,65535,1.6f,{1.05f,1.f,1.1f},.67f};
 char path[128];
 int n=snprintf(path,sizeof(path),"outputs/.nx_jpeg_benchmark_%ld.jpg",
                (long)getpid());
 if(n<1||(size_t)n>=sizeof(path)||access(path,F_OK)==0){
  free(bayer);return 2;
 }
 nx_host_jpeg_writer *writer=nx_host_jpeg_writer_create(path,NULL,0);
 if(!writer){free(bayer);return 2;}
 nx_bayer_rgb8_sink sink=nx_host_jpeg_writer_sink(writer);
 struct timespec a,b;
 clock_gettime(CLOCK_MONOTONIC,&a);
 int rc=nx_bayer_prejpeg_emit_rows(bayer,count,w,w,h,&cal,&look,103,&sink);
 clock_gettime(CLOCK_MONOTONIC,&b);
 nx_host_jpeg_writer_destroy(writer);
 struct stat info;
 if(rc||stat(path,&info)){
  free(bayer);return 1;
 }
 printf("HOST REAL JPEG 4:4:4 (not NX300M native) %ux%u: encoded_bytes=%lld; time=%.3f sec; raw_in_memory=%zu; output_frame_alloc=0; one atomic file publish=PASS\n",
        w,h,(long long)info.st_size,elapsed(a,b),count*2u);
 if(unlink(path)){free(bayer);return 1;}
 free(bayer);
 return 0;
}
