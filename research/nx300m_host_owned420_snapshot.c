#include "nx300m_host_owned420_snapshot.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define SNAPSHOT_MAX_BYTES ((size_t)128u * 1024u * 1024u)

/* This bounds arithmetic and rejects simulated aliases. It cannot check
 * that a forged caller-supplied pointer is mapped to real readable memory.
 */
static int invalid_span(const void *p,size_t n){
    return !p||n==0u||n>UINTPTR_MAX-(uintptr_t)p;
}
static int overlap(const void *a,size_t an,const void *b,size_t bn){
    const uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x<y+bn&&y<x+an;
}
static int budget_add(size_t *total,size_t n){
    if(n>SNAPSHOT_MAX_BYTES-*total)return -1;
    *total+=n;
    return 0;
}
void nx_host_owned420_snapshot_release(nx_host_owned420_snapshot *s){
    if(!s)return;
    free(s->owned_y);
    free(s->owned_chroma);
    free(s->owned_lut);
    free(s->owned_decode);
    free(s->owned_encode);
    memset(s,0,sizeof(*s));
}
int nx_host_owned420_snapshot_take(
    nx_host_owned420_snapshot *out,
    const nx_film_owned420_hypothesis_job *j){
    if(!out)return -1;
    /* The output is caller-owned and must be zero-initialized. */
    memset(out,0,sizeof(*out));
    if(!j||j->copy_declaration!=NX_FILM_420_COPY_DECLARATION||
       (j->hypothesis!=NX_FILM_BT601_FULL_CBCR_HYPOTHESIS&&
        j->hypothesis!=NX_FILM_BT601_FULL_CRCB_HYPOTHESIS)||
       j->width<4u||j->width>8192u||(j->width&1u)||
       j->height<4u||j->height>8192u||(j->height&1u)||
       j->grid<2u||j->grid>65u||
       j->y_stride<j->width||j->chroma_stride<j->width||
       j->y_stride>65536u||j->chroma_stride>65536u||
       j->decode_entries!=256u||j->encode_entries!=4096u)
        return -1;
    const size_t grid=(size_t)j->grid;
    const size_t nodes=grid*grid*grid;
    if(j->lut_nodes<nodes)return -1;

    /* Copy the actually accessed span, including intermediate row gaps.
     * Do not read advertised trailing padding after the final image row. */
    const size_t yn=((size_t)j->height-1u)*j->y_stride+j->width;
    const size_t cn=((size_t)j->height/2u-1u)*j->chroma_stride+j->width;
    const size_t ln=nodes*sizeof(nx_rgb12);
    const size_t dn=256u*sizeof(uint16_t);
    const size_t en=4096u;
    if(yn>j->y_bytes||cn>j->chroma_bytes)return -1;
    const void *const sources[5]={
        j->y,j->chroma,j->lut,j->decode_srgb,j->encode_srgb
    };
    const size_t spans[5]={yn,cn,ln,dn,en};
    size_t total=0u;
    for(unsigned i=0;i<5u;i++){
        if(invalid_span(sources[i],spans[i])||
           budget_add(&total,spans[i])!=0)return -1;
        for(unsigned k=0;k<i;k++)
            if(overlap(sources[i],spans[i],sources[k],spans[k]))
                return -1;
    }
    /* Refuse nonsensical host input before allocating. No camera
     * pixel-buffer range is inferred from the supplied metadata. */
    for(unsigned i=0;i<256u;i++)
        if(j->decode_srgb[i]>4095u)return -1;

    out->owned_y=malloc(yn);
    out->owned_chroma=malloc(cn);
    out->owned_lut=malloc(ln);
    out->owned_decode=malloc(dn);
    out->owned_encode=malloc(en);
    if(!out->owned_y||!out->owned_chroma||!out->owned_lut||
       !out->owned_decode||!out->owned_encode){
        nx_host_owned420_snapshot_release(out);
        return -1;
    }
    memcpy(out->owned_y,j->y,yn);
    memcpy(out->owned_chroma,j->chroma,cn);
    memcpy(out->owned_lut,j->lut,ln);
    memcpy(out->owned_decode,j->decode_srgb,dn);
    memcpy(out->owned_encode,j->encode_srgb,en);
    out->job=*j;
    out->job.y=out->owned_y;
    out->job.y_bytes=yn;
    out->job.chroma=out->owned_chroma;
    out->job.chroma_bytes=cn;
    out->job.lut=out->owned_lut;
    out->job.lut_nodes=nodes;
    out->job.decode_srgb=out->owned_decode;
    out->job.encode_srgb=out->owned_encode;
    out->job.rgb=NULL;        /* The JPEG adapter supplies one output row. */
    out->job.rgb_bytes=0u;
    out->job.rgb_stride=0u;
    return 0;
}
