#define _POSIX_C_SOURCE 200809L
#include "nx300m_host_420_film_jpeg.h"
#include "nx300m_host_native420_bridge.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum { W=28,H=20,STRIDE=36,LOOKS=2,ORDERS=2 };
static const uint8_t app1[]={
  'E','x','i','f',0,0,'I','I',42,0,8,0,0,0,0,0,0,0,0,0
};
static uint8_t reference[H][W*3u];
static uint64_t read_jpeg(const char *path,size_t *size,int *has_exif){
 FILE *f=fopen(path,"rb");
 assert(f);
 uint64_t hash=UINT64_C(14695981039346656037);
 uint8_t prev=0,first=0,second=0,previous=0;
 uint8_t window[sizeof(app1)]={0};
 size_t n=0;
 int ch;
 *has_exif=0;
 while((ch=fgetc(f))!=EOF){
   uint8_t c=(uint8_t)ch;
   if(n==0)first=c;
   if(n==1)second=c;
   memmove(window,window+1,sizeof(window)-1);
   window[sizeof(window)-1]=c;
   if(n+1>=sizeof(window)&&memcmp(window,app1,sizeof(window))==0)
      *has_exif=1;
   previous=prev;prev=c;
   hash^=c;hash*=UINT64_C(1099511628211);
   n++;
 }
 assert(!ferror(f));
 assert(fclose(f)==0);
 assert(n>350&&first==255u&&second==216u&&previous==255u&&prev==217u);
 *size=n;
 return hash;
}
int main(void){
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){
  uint8_t *p=reference[y]+3u*x;
  p[0]=(uint8_t)((x*27u+y*7u)%256u);
  p[1]=(uint8_t)((x*4u+y*19u)%256u);
  p[2]=(uint8_t)((x*13u+y*31u)%256u);
 }
 uint64_t hashes[ORDERS][LOOKS]={0};
 size_t sizes[ORDERS][LOOKS]={0};
 char paths[ORDERS][LOOKS][128];
 for(unsigned order=0;order<ORDERS;order++){
  nx_host420_stage *stage=nx_host420_create(W,H,STRIDE,
       order?NX_HOST420_CRCB_EXPERIMENTAL:NX_HOST420_CBCR_EXPERIMENTAL);
  assert(stage);
  nx_bayer_rgb8_sink s=nx_host420_sink(stage);
  assert(s.begin(s.user,W,H,103)==0);
  for(unsigned y=0;y<H;y++)
    assert(s.write_row(s.user,y,reference[y],W*3u)==0);
  assert(s.commit(s.user)==0);
  size_t bytes=0;
  nx_native_cycc synthetic;
  const uint8_t *frame=nx_host420_published(stage,&bytes,&synthetic);
  assert(frame&&bytes==2u*STRIDE*H);
  assert(synthetic.width==W&&synthetic.height==H&&synthetic.stride==STRIDE);
  uint8_t *snapshot=malloc(bytes);
  assert(snapshot);
  memcpy(snapshot,frame,bytes);
  const uint8_t *y=frame;
  const uint8_t *c=frame+(size_t)STRIDE*H;
  for(unsigned i=0;i<LOOKS;i++){
   const unsigned film_id=i?204u:101u;
   assert(snprintf(paths[order][i],sizeof(paths[order][i]),
       "outputs/nx_host420_film_%ld_%u_%u.jpg",
       (long)getpid(),order,film_id)>0);
   assert(access(paths[order][i],F_OK)!=0);
   const int rc=nx_host420_film_to_jpeg(y,STRIDE*H,STRIDE,c,
       STRIDE*(H/2u),STRIDE,W,H,
       order?NX_HOST420_CRCB_EXPERIMENTAL:NX_HOST420_CBCR_EXPERIMENTAL,
       film_id,paths[order][i],app1,sizeof(app1));
   assert(rc==0);
   int present=0;
   hashes[order][i]=read_jpeg(paths[order][i],&sizes[order][i],&present);
   assert(present);
   /* Host 420 -> film engine changes the RGB pixels BEFORE JPEG coding. */
   assert(sizes[order][i]>350);
   assert(memcmp(snapshot,frame,bytes)==0);
   /* The writer must refuse an existing file, and must not truncate it. */
   assert(nx_host420_film_to_jpeg(y,STRIDE*H,STRIDE,c,
       STRIDE*(H/2u),STRIDE,W,H,
       order?NX_HOST420_CRCB_EXPERIMENTAL:NX_HOST420_CBCR_EXPERIMENTAL,
       film_id,paths[order][i],app1,sizeof(app1))==-1);
   size_t repeat=0;int repeat_exif=0;
   assert(read_jpeg(paths[order][i],&repeat,&repeat_exif)==hashes[order][i]);
   assert(repeat==sizes[order][i]&&repeat_exif);
  }
  assert(hashes[order][0]!=hashes[order][1]);
  const char *no_output="outputs/.nx_host420_original_must_not_exist.jpg";
  assert(access(no_output,F_OK)!=0);
  assert(nx_host420_film_to_jpeg(y,STRIDE*H,STRIDE,c,STRIDE*(H/2u),
      STRIDE,W,H,NX_HOST420_CBCR_EXPERIMENTAL,0,no_output,NULL,0)==1);
  assert(access(no_output,F_OK)!=0);
  const char *bad="outputs/.nx_host420_invalid_must_not_exist.jpg";
  assert(access(bad,F_OK)!=0);
  assert(nx_host420_film_to_jpeg(y,STRIDE*H,STRIDE,c,
     STRIDE*(H/2u),STRIDE,W,H,NX_HOST420_ORDER_UNSPECIFIED,
     101,bad,NULL,0)==-1);
  assert(nx_host420_film_to_jpeg(y,(H-1u)*STRIDE+W-1u,STRIDE,c,
     STRIDE*(H/2u),STRIDE,W,H,NX_HOST420_CBCR_EXPERIMENTAL,
     101,bad,NULL,0)==-1);
  assert(nx_host420_film_to_jpeg(y,1,STRIDE,c,
     STRIDE*(H/2u),STRIDE,W,H,NX_HOST420_CBCR_EXPERIMENTAL,
     101,bad,NULL,0)==-1);
  assert(nx_host420_film_to_jpeg(y,STRIDE*H,STRIDE,c,1,
     STRIDE,W,H,NX_HOST420_CBCR_EXPERIMENTAL,
     101,bad,NULL,0)==-1);
  assert(nx_host420_film_to_jpeg(y,STRIDE*H,STRIDE,c,
     STRIDE*(H/2u),STRIDE,W-1,H,NX_HOST420_CBCR_EXPERIMENTAL,
     101,bad,NULL,0)==-1);
  assert(nx_host420_film_to_jpeg(y,STRIDE*H,STRIDE,c,
     STRIDE*(H/2u),STRIDE,W,H,NX_HOST420_CBCR_EXPERIMENTAL,
     999,bad,NULL,0)==-1);
  const uint8_t invalid_exif[]={'B','A','D'};
  assert(nx_host420_film_to_jpeg(y,STRIDE*H,STRIDE,c,
     STRIDE*(H/2u),STRIDE,W,H,NX_HOST420_CBCR_EXPERIMENTAL,
     101,bad,invalid_exif,sizeof(invalid_exif))==-1);
  assert(memcmp(snapshot,frame,bytes)==0);
  free(snapshot);
  nx_host420_destroy(stage);
 }
 /* Same RGB -> either host CbCr or CrCb layout decodes to identical RGB
  * and identical filtered JPEG after selecting explicit byte order. */
 for(unsigned i=0;i<LOOKS;i++){
  assert(hashes[0][i]==hashes[1][i]);
 }
 for(unsigned order=0;order<ORDERS;order++)
  for(unsigned i=0;i<LOOKS;i++)assert(unlink(paths[order][i])==0);
 puts("PASS HOST 420 input -> independent film pixel transform -> 4 real JPEGs; explicit chroma order; original Y/C unchanged; original bypass; overwrite/invalid rejected; no camera DMA");
 return 0;
}
