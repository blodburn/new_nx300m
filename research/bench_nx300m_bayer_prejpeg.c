#define _POSIX_C_SOURCE 200809L
#include "nx300m_bayer_prejpeg.h"
#include <time.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

static double elapsed(struct timespec a,struct timespec b){
 return (double)(b.tv_sec-a.tv_sec)+1.e-9*(double)(b.tv_nsec-a.tv_nsec);
}
typedef struct {
 uint64_t hash;
 unsigned width,height,next_y,committed;
 uint8_t first,last;
} hash_sink;
static int hash_begin(void *user,unsigned width,unsigned height,unsigned id){
 hash_sink *s=user;
 if(id!=103||!width||!height)return -1;
 s->width=width;s->height=height;s->next_y=0;
 s->hash=UINT64_C(14695981039346656037);
 s->committed=0;
 return 0;
}
static int hash_row(void *user,unsigned y,const uint8_t *row,size_t len){
 hash_sink *s=user;
 if(!row||y!=s->next_y||len!=(size_t)s->width*3u)return -1;
 if(y==0)s->first=row[0];
 s->last=row[len-1];
 for(size_t i=0;i<len;i++){
  s->hash^=row[i];s->hash*=UINT64_C(1099511628211);
 }
 s->next_y++;
 return 0;
}
static int hash_commit(void *user){
 hash_sink *s=user;
 if(s->next_y!=s->height)return -1;
 s->committed=1;
 return 0;
}
static void hash_abort(void *user){
 hash_sink *s=user;s->committed=0;
}
int main(int argc,char **argv){
 enum {W=5546,H=3714};
 size_t count=(size_t)W*H;
 uint16_t *raw=malloc(count*sizeof(*raw));
 int emit=argc>1&&strcmp(argv[1],"emit")==0;
 uint8_t *out=emit?NULL:malloc(count*3u);
 if(!raw||(!emit&&!out)){free(raw);free(out);return 2;}
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++)
   raw[(size_t)y*W+x]=(uint16_t)(12000+(x/5u)%34000u);
 nx_bayer_calibration cal={NX_BAYER_RGGB,{64,64,64,64},
                            {60000,60000,60000,60000},2200};
 nx_linear_params look={0,65535,1.6f,{1.05f,1.f,1.1f},.67f};
 struct timespec a,b;
 clock_gettime(CLOCK_MONOTONIC,&a);
 int stream=argc>1&&strcmp(argv[1],"stream")==0;
 hash_sink sink_state={0};
 nx_bayer_rgb8_sink sink={hash_begin,hash_row,hash_commit,hash_abort,&sink_state};
 int rc=emit?
    nx_bayer_prejpeg_emit_rows(raw,count,W,W,H,&cal,&look,103,&sink):
    stream?
    nx_bayer_prejpeg_film_streaming(raw,count,W,out,count*3u,(size_t)W*3u,
                                    W,H,&cal,&look,103):
    nx_bayer_prejpeg_film(raw,count,W,out,count*3u,(size_t)W*3u,
                          W,H,&cal,&look,103);
 clock_gettime(CLOCK_MONOTONIC,&b);
 uint64_t hash=UINT64_C(14695981039346656037);
 if(rc==0&&!emit)
  for(size_t i=0;i<count*3u;i++){
   hash^=out[i];
   hash*=UINT64_C(1099511628211);
  }
 if(emit)hash=sink_state.hash;
 printf("HOST SYNTHETIC %s %ux%u: rc=%d, time=%.3f sec, Bayer input=%zu bytes, RGB16 scratch=%zu bytes, final RGB8 allocation=%zu bytes, style luma=%zu bytes, pixel[0]=%u, pixel[end]=%u, rgb8_fnv64=%016llx, committed=%u\n",
        emit?"EMIT":stream?"STREAM":"FULL",W,H,rc,elapsed(a,b),count*sizeof(uint16_t),
        (emit||stream)?(size_t)W*3u*sizeof(uint16_t):count*3u*sizeof(uint16_t),
        emit?0:count*3u,(emit||stream)?(size_t)W*3u:count,
        emit?sink_state.first:out[0],emit?sink_state.last:out[count*3u-1u],
        (unsigned long long)hash,emit?sink_state.committed:0);
 free(raw);free(out);
 return rc!=0;
}
