/* HOST-ONLY Y/C420 snapshot tests. No camera, kernel mapping, or firmware. */
#include "nx300m_host_owned420_snapshot.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { W=32,H=24,YS=40,CS=42 };
static uint8_t y[YS*H],c[CS*(H/2u)],encode[4096];
static uint16_t decode[256];
static nx_rgb12 lut[8];

static nx_film_owned420_hypothesis_job fixture(void){
    for(size_t i=0;i<sizeof(y);i++)y[i]=(uint8_t)(i*17u+3u);
    for(size_t i=0;i<sizeof(c);i++)c[i]=(uint8_t)(i*11u+5u);
    for(size_t i=0;i<sizeof(encode);i++)encode[i]=(uint8_t)(i/16u);
    for(size_t i=0;i<256u;i++)decode[i]=(uint16_t)(i*16u);
    for(size_t i=0;i<8u;i++)lut[i]=(nx_rgb12){
        (uint16_t)(i*300u),(uint16_t)(i*220u),
        (uint16_t)(i*160u),0u
    };
    nx_film_owned420_hypothesis_job j={0};
    j.copy_declaration=NX_FILM_420_COPY_DECLARATION;
    j.hypothesis=NX_FILM_BT601_FULL_CBCR_HYPOTHESIS;
    j.y=y;j.y_bytes=sizeof(y);j.y_stride=YS;
    j.chroma=c;j.chroma_bytes=sizeof(c);j.chroma_stride=CS;
    j.width=W;j.height=H;
    j.lut=lut;j.lut_nodes=8u;j.grid=2u;
    j.decode_srgb=decode;j.decode_entries=256u;
    j.encode_srgb=encode;j.encode_entries=4096u;
    return j;
}
static void verify_detachment(void){
    nx_film_owned420_hypothesis_job j=fixture();
    nx_host_owned420_snapshot s={0};
    const size_t yn=(H-1u)*YS+W;
    const size_t cn=(H/2u-1u)*CS+W;
    assert(nx_host_owned420_snapshot_take(&s,&j)==0);
    assert(nx_host_owned420_snapshot_ready(&s)==1);
    /* A second take may not drop the first owned allocation. */
    const uint8_t *first_owned_y=s.owned_y;
    assert(nx_host_owned420_snapshot_take(&s,&j)==-1);
    assert(s.owned_y==first_owned_y&&nx_host_owned420_snapshot_ready(&s));
    s.job.y_bytes--;
    assert(!nx_host_owned420_snapshot_ready(&s));
    s.job.y_bytes++;
    assert(nx_host_owned420_snapshot_ready(&s));
    assert(s.job.y!=j.y&&s.job.chroma!=j.chroma);
    assert(s.job.lut!=j.lut&&s.job.decode_srgb!=j.decode_srgb);
    assert(s.job.encode_srgb!=j.encode_srgb);
    assert(s.job.y_bytes==yn&&s.job.chroma_bytes==cn);
    assert(s.job.lut_nodes==8u&&s.job.rgb==NULL);
    assert(memcmp(s.job.y,y,yn)==0&&memcmp(s.job.chroma,c,cn)==0);
    assert(memcmp(s.job.lut,lut,sizeof(lut))==0);
    assert(memcmp(s.job.decode_srgb,decode,sizeof(decode))==0);
    assert(memcmp(s.job.encode_srgb,encode,sizeof(encode))==0);
    const uint8_t y0=s.job.y[0],c0=s.job.chroma[0];
    const uint16_t d0=s.job.decode_srgb[1];
    const nx_rgb12 l0=s.job.lut[0];
    const uint8_t e0=s.job.encode_srgb[0];
    memset(y,0,sizeof(y));memset(c,0,sizeof(c));
    memset(lut,0xff,sizeof(lut));memset(decode,0xff,sizeof(decode));
    memset(encode,0xff,sizeof(encode));
    assert(s.job.y[0]==y0&&s.job.chroma[0]==c0);
    assert(s.job.decode_srgb[1]==d0);
    assert(memcmp(&s.job.lut[0],&l0,sizeof(l0))==0);
    assert(s.job.encode_srgb[0]==e0);
    nx_host_owned420_snapshot_release(&s);
    assert(s.owned_y==NULL&&s.owned_chroma==NULL&&s.owned_lut==NULL);
    assert(s.job.y==NULL&&s.job.chroma==NULL);
    puts("PASS independent source snapshot survives changes to every caller buffer");
}
static void verify_invalid_metadata(void){
    for(unsigned i=0;i<13u;i++){
        nx_film_owned420_hypothesis_job j=fixture();
        switch(i){
        case 0:j.copy_declaration=0u;break;
        case 1:j.hypothesis=0u;break;
        case 2:j.y_bytes=YS;break;
        case 3:j.chroma_bytes=CS;break;
        case 4:j.y_stride=W-1u;break;
        case 5:j.height=H-1u;break;
        case 6:j.grid=66u;break;
        case 7:j.lut_nodes=7u;break;
        case 8:j.decode_entries=255u;break;
        case 9:j.encode_entries=4095u;break;
        case 10:j.chroma=y;j.chroma_bytes=sizeof(y);break;
        case 11:decode[7]=4096u;break;
        case 12:
            /* Fake oversized host spans must be rejected by budget BEFORE
             * any attempted read from our small backing test arrays. */
            j.width=8192u;j.height=8192u;
            j.y_stride=16384u;j.chroma_stride=16384u;
            j.y_bytes=256u*1024u*1024u;
            j.chroma_bytes=256u*1024u*1024u;
            break;
        }
        nx_host_owned420_snapshot s={0};
        assert(nx_host_owned420_snapshot_take(&s,&j)==-1);
        assert(s.owned_y==NULL&&s.owned_chroma==NULL);
        assert(s.owned_lut==NULL&&s.owned_decode==NULL);
        assert(s.owned_encode==NULL);
        nx_host_owned420_snapshot_release(&s);
    }
    assert(nx_host_owned420_snapshot_take(NULL,NULL)==-1);
    puts("PASS 13 fail-closed metadata/bounds/alias/budget cases");
}
static void verify_aliased_output_is_never_modified(void){
    nx_film_owned420_hypothesis_job j=fixture();
    const unsigned prior_id=j.copy_declaration;
    /* The original implementation memset(out) before checking this alias. */
    nx_host_owned420_snapshot *job_alias=(nx_host_owned420_snapshot *)(void *)&j;
    assert(nx_host_owned420_snapshot_take(job_alias,&j)==-1);
    assert(j.copy_declaration==prior_id);
    assert(j.y==y&&j.chroma==c);

    nx_host_owned420_snapshot live={0};
    j.y=(const uint8_t *)&live;
    j.y_bytes=YS*H;
    assert(nx_host_owned420_snapshot_take(&live,&j)==-1);
    assert(live.owned_y==NULL&&live.job.y==NULL);
    assert(live.owned_lut==NULL&&live.owned_decode==NULL);
    puts("PASS alias to input job/output buffer rejected before all writes");
}

int main(void){
    verify_detachment();
    verify_invalid_metadata();
    verify_aliased_output_is_never_modified();
    puts("PASS host-owned420 snapshot boundary; camera memory/DMA unverified");
    return 0;
}
