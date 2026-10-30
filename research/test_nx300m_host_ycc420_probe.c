#include "nx300m_host_ycc420_probe.h"
#include "nx300m_host_native420_bridge.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
enum {W=24,H=16,STRIDE=32,RGB_STRIDE=W*3+5,FRAME_BYTES=2*STRIDE*H};
static uint8_t rgb[H*RGB_STRIDE], rgb_backup[H*RGB_STRIDE];
static uint8_t stage_backup[FRAME_BYTES], corrupt[FRAME_BYTES];
static void generate_rgb(int neutral){
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){
  const unsigned selector=(x/2u+(y/2u)*3u)%6u;
  const uint8_t colors[6][3]={
   {240,32,16},{20,60,245},{20,220,38},
   {245,160,12},{175,18,225},{35,212,220}
  };
  uint8_t *pixel=rgb+(size_t)y*RGB_STRIDE+3u*x;
  for(unsigned k=0;k<3;k++)pixel[k]=neutral?128:colors[selector][k];
 }
 memcpy(rgb_backup,rgb,sizeof(rgb));
}
static void test_order(enum nx_host420_order order){
 nx_host420_stage *s=nx_host420_create(W,H,STRIDE,order);
 assert(s);
 nx_bayer_rgb8_sink sink=nx_host420_sink(s);
 assert(sink.begin(sink.user,W,H,103)==0);
 for(unsigned y=0;y<H;y++)
  assert(sink.write_row(sink.user,y,rgb+(size_t)y*RGB_STRIDE,(size_t)W*3u)==0);
 assert(sink.commit(sink.user)==0);
 size_t len=0;nx_native_cycc head;
 const uint8_t *stage=nx_host420_published(s,&len,&head);
 assert(stage&&len==sizeof(stage_backup));
 memcpy(stage_backup,stage,len);
 nx_ycc420_evidence e;
 const nx_ycc420_assessment result=nx_host_ycc420_probe(
   stage,(size_t)STRIDE*H,STRIDE,
   stage+(size_t)STRIDE*H,(size_t)STRIDE*H,STRIDE,
   rgb,sizeof(rgb),RGB_STRIDE,W,H,&e);
 assert(result==(order==NX_HOST420_CBCR_EXPERIMENTAL?
                 NX_YCC420_CBCR:NX_YCC420_CRCB));
 assert(e.result==result&&e.pixels==(uint64_t)W*H);
 assert(e.chroma_pairs==(uint64_t)W*H/4);
 assert(e.y_mae_milli==0&&e.informative_pairs>8);
 assert(e.winning_gap_milli>6000);
 assert(!memcmp(stage,stage_backup,len));
 assert(!memcmp(rgb,rgb_backup,sizeof(rgb)));
 assert(nx_host_ycc420_probe(stage,STRIDE*H-1u,STRIDE,
           stage+STRIDE*H,STRIDE*H,STRIDE,
           rgb,sizeof(rgb),RGB_STRIDE,W,H,&e)==NX_YCC420_CBCR ||
        e.result==NX_YCC420_CRCB);
 /* Actually truncate into last luma active row to force fail closed. */
 assert(nx_host_ycc420_probe(stage,(size_t)(H-1)*STRIDE+W-1,STRIDE,
           stage+STRIDE*H,STRIDE*H,STRIDE,
           rgb,sizeof(rgb),RGB_STRIDE,W,H,&e)==NX_YCC420_BAD_INPUT);
 assert(nx_host_ycc420_probe(stage,STRIDE*H,STRIDE,
           stage+STRIDE*H,(size_t)(H/2-1)*STRIDE+W-1,STRIDE,
           rgb,sizeof(rgb),RGB_STRIDE,W,H,&e)==NX_YCC420_BAD_INPUT);
 assert(nx_host_ycc420_probe(stage,STRIDE*H,STRIDE,
           stage+STRIDE*H,STRIDE*H,STRIDE,
           rgb,sizeof(rgb)-RGB_STRIDE,RGB_STRIDE,W,H,&e)==NX_YCC420_BAD_INPUT);
 assert(nx_host_ycc420_probe(stage,STRIDE*H,STRIDE,
           stage+STRIDE*H,STRIDE*H,STRIDE,
           rgb,sizeof(rgb),RGB_STRIDE,W-1,H,&e)==NX_YCC420_BAD_INPUT);
 assert(nx_host_ycc420_probe(stage,STRIDE*H,STRIDE,
           stage+STRIDE*H,STRIDE*H,STRIDE,
           rgb,sizeof(rgb),RGB_STRIDE,W,H,NULL)==NX_YCC420_BAD_INPUT);
 /* Not same RGB stage: if luma and reference diverge, abstain. */
 memcpy(corrupt,stage,len);
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++)
  corrupt[(size_t)y*STRIDE+x]=255;
 assert(nx_host_ycc420_probe(corrupt,STRIDE*H,STRIDE,
           corrupt+STRIDE*H,STRIDE*H,STRIDE,
           rgb,sizeof(rgb),RGB_STRIDE,W,H,&e)==NX_YCC420_INCONCLUSIVE);
 /* Not the two modeled interleaving layouts: abstain. */
 memcpy(corrupt,stage,len);
 for(unsigned y=0;y<H/2;y++)for(unsigned x=0;x<W;x++)
  corrupt[(size_t)STRIDE*H+(size_t)y*STRIDE+x]=0;
 assert(nx_host_ycc420_probe(corrupt,STRIDE*H,STRIDE,
           corrupt+STRIDE*H,STRIDE*H,STRIDE,
           rgb,sizeof(rgb),RGB_STRIDE,W,H,&e)==NX_YCC420_INCONCLUSIVE);
 assert(!memcmp(stage,stage_backup,len));
 nx_host420_destroy(s);
}
int main(void){
 generate_rgb(0);
 test_order(NX_HOST420_CBCR_EXPERIMENTAL);
 test_order(NX_HOST420_CRCB_EXPERIMENTAL);
 /* Gray is symmetric Cb=Cr; cannot distinguish byte order. */
 generate_rgb(1);
 nx_host420_stage *s=nx_host420_create(W,H,STRIDE,NX_HOST420_CBCR_EXPERIMENTAL);
 assert(s);
 nx_bayer_rgb8_sink sink=nx_host420_sink(s);
 assert(sink.begin(sink.user,W,H,103)==0);
 for(unsigned y=0;y<H;y++)
  assert(sink.write_row(sink.user,y,rgb+(size_t)y*RGB_STRIDE,W*3u)==0);
 assert(sink.commit(sink.user)==0);
 size_t bytes=0;nx_native_cycc meta;
 const uint8_t *stage=nx_host420_published(s,&bytes,&meta);
 assert(stage);
 nx_ycc420_evidence e;
 assert(nx_host_ycc420_probe(stage,STRIDE*H,STRIDE,
             stage+STRIDE*H,STRIDE*H,STRIDE,
             rgb,sizeof(rgb),RGB_STRIDE,W,H,&e)==NX_YCC420_INCONCLUSIVE);
 assert(e.informative_pairs==0&&e.winning_gap_milli==0);
 nx_host420_destroy(s);
 puts("PASS read-only YCC420 evidence gate: both chroma orders, neutral ambiguity, matrix mismatch rejection, unknown packing rejection, bounds, no input writes");
 return 0;
}
