#include "nx300m_bayer_prejpeg.h"
#include "nx300m_film_menu.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum {W=16,H=12,S=19};
static uint16_t bayer[H*S],preserved[H*S];
static uint8_t full[H*W*3u],staged[H*W*3u];
static nx_bayer_calibration cal={NX_BAYER_RGGB,
 {64,96,72,80},{60000,61000,62000,63000},2200};
static nx_linear_params look={0,65535,2.f,{1.1f,1.f,0.85f},.6f};
typedef struct {
 unsigned begin_calls,row_calls,commit_calls,abort_calls,active,published;
 unsigned width,height,film_id;
 int fail_begin,fail_row,fail_commit;
} txn;
static int begin(void *v,unsigned w,unsigned h,unsigned id){
 txn *s=v;
 s->begin_calls++;
 s->width=w;s->height=h;s->film_id=id;
 if(s->fail_begin)return -1;
 s->active=1;
 memset(staged,0xcd,sizeof(staged));
 return 0;
}
static int write_row(void *v,unsigned y,const uint8_t *row,size_t bytes){
 txn *s=v;
 assert(s->active&&!s->published&&row);
 assert(y==s->row_calls);
 assert(bytes==(size_t)s->width*3u);
 if(s->fail_row>=0&&(int)y==s->fail_row)return -1;
 memcpy(staged+(size_t)y*bytes,row,bytes);
 s->row_calls++;
 return 0;
}
static int commit(void *v){
 txn *s=v;
 s->commit_calls++;
 assert(s->active&&s->row_calls==s->height);
 if(s->fail_commit)return -1;
 s->published=1;s->active=0;
 return 0;
}
static void abort_txn(void *v){
 txn *s=v;
 s->abort_calls++;
 s->active=0;s->published=0;
 memset(staged,0xe7,sizeof(staged));
}
static nx_bayer_rgb8_sink make_sink(txn *s){
 nx_bayer_rgb8_sink sink={begin,write_row,commit,abort_txn,s};
 return sink;
}
static void make_bayer(unsigned w,unsigned h,unsigned scene){
 memset(bayer,0xfe,sizeof(bayer));
 for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++){
  unsigned site=((y&1u)<<1u)|(x&1u);
  unsigned intensity=(scene==0?20000u+500u*(x%5u):
     scene==1?(x<w/2?9000u:43000u):
      (y<h/2?12000u+(x%3u)*1500u:55000u-(x%4u)*1800u));
  bayer[(size_t)y*S+x]=(uint16_t)(cal.black[site]+
     ((uint64_t)intensity*(cal.white[site]-cal.black[site])+32767u)/65535u);
 }
 memcpy(preserved,bayer,sizeof(bayer));
}
int main(void){
 unsigned comparisons=0;
 for(unsigned pat=0;pat<4;pat++)for(unsigned sc=0;sc<3;sc++){
  cal.pattern=(nx_bayer_pattern)pat;
  const unsigned w=sc==2?W-1:W,h=sc==2?H-1:H;
  make_bayer(w,h,sc);
  for(size_t i=1;i<nx_film_count();i++){
   const nx_film_preset *profile=nx_film_by_index(i);
   assert(profile&&profile->id!=0);
   memset(full,0xaf,sizeof(full));
   assert(nx_bayer_prejpeg_film(bayer,H*S,S,full,(size_t)w*h*3u,
                                (size_t)w*3u,w,h,&cal,&look,profile->id)==0);
   txn t={0};t.fail_row=-1;
   nx_bayer_rgb8_sink sink=make_sink(&t);
   assert(nx_bayer_prejpeg_emit_rows(bayer,H*S,S,w,h,&cal,&look,
                                    profile->id,&sink)==0);
   assert(t.begin_calls==1&&t.row_calls==h&&t.commit_calls==1);
   assert(t.abort_calls==0&&t.published==1);
   assert(!memcmp(full,staged,(size_t)w*h*3u));
   assert(!memcmp(bayer,preserved,sizeof(bayer)));
   comparisons++;
  }
 }
 cal.pattern=NX_BAYER_RGGB;
 make_bayer(W,H,0);
 txn t={0};t.fail_row=-1;
 nx_bayer_rgb8_sink sink=make_sink(&t);
 /* Samsung original is no-op and can omit every sink callback. */
 assert(nx_bayer_prejpeg_emit_rows(bayer,H*S,S,W,H,&cal,&look,0,NULL)==1);
 assert(!t.begin_calls);
 /* Reject invalid metadata before begin, never alter RAW. */
 nx_bayer_calibration invalid=cal;invalid.white[0]=invalid.black[0];
 assert(nx_bayer_prejpeg_emit_rows(bayer,H*S,S,W,H,&invalid,&look,101,&sink)==-1);
 assert(nx_bayer_prejpeg_emit_rows(bayer,H*S-1,S,W,H,&cal,&look,101,&sink)==-1);
 assert(nx_bayer_prejpeg_emit_rows(bayer,H*S,S,W,H,&cal,&look,999,&sink)==-1);
 nx_linear_params bad=look;bad.exposure=9.f;
 assert(nx_bayer_prejpeg_emit_rows(bayer,H*S,S,W,H,&cal,&bad,101,&sink)==-1);
 assert(nx_bayer_prejpeg_emit_rows(bayer,H*S,S,W,H,&cal,&look,101,NULL)==-1);
 assert(!t.begin_calls);
 /* Fail-closed sink: no commit on row failure. Temp stage is destroyed. */
 for(int failing=0;failing<H;failing++){
  txn fail={0};fail.fail_row=failing;
  sink=make_sink(&fail);
  assert(nx_bayer_prejpeg_emit_rows(bayer,H*S,S,W,H,&cal,&look,101,&sink)==-1);
  assert(fail.begin_calls==1&&fail.row_calls==(unsigned)failing);
  assert(fail.commit_calls==0&&fail.abort_calls==1&&!fail.published);
  for(size_t i=0;i<sizeof(staged);i++)assert(staged[i]==0xe7);
 }
 txn fail_begin={0};fail_begin.fail_row=-1;fail_begin.fail_begin=1;
 sink=make_sink(&fail_begin);
 assert(nx_bayer_prejpeg_emit_rows(bayer,H*S,S,W,H,&cal,&look,101,&sink)==-1);
 assert(fail_begin.begin_calls==1&&fail_begin.row_calls==0&&
        fail_begin.commit_calls==0&&fail_begin.abort_calls==1);
 txn fail_commit={0};fail_commit.fail_row=-1;fail_commit.fail_commit=1;
 sink=make_sink(&fail_commit);
 assert(nx_bayer_prejpeg_emit_rows(bayer,H*S,S,W,H,&cal,&look,101,&sink)==-1);
 assert(fail_commit.row_calls==H&&fail_commit.commit_calls==1&&
        fail_commit.abort_calls==1&&!fail_commit.published);
 assert(!memcmp(bayer,preserved,sizeof(bayer)));
 printf("PASS %u byte-exact 4-CFA x 3-scenes x 12-looks callbacks, Original untouched, invalid no begin, 12 row-fail aborts, begin/commit fail-safe; single commit only on success\n",
        comparisons);
 return 0;
}
