#define _POSIX_C_SOURCE 200809L
/* Independent HOST Bayer -> film pixel transforms -> actual baseline JPEG.
 * This is not a Samsung camera pipeline, ISP patch or native Picture Wizard.
 * Run with --keep to inspect three generated JPGs in outputs/.
 */
#include "nx300m_bayer_prejpeg.h"
#include "nx300m_host_jpeg_sink.h"
#include "nx300m_film_menu.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum { W=37,H=29,STRIDE=40,LOOKS=3 };
static uint16_t bayer[H*STRIDE],original[H*STRIDE];
static uint8_t processed[LOOKS][W*H*3];
static const unsigned ids[LOOKS]={101,105,204}; /* Fuji vivid/cinema, Leica HC mono */

static uint64_t hash_jpg(const char *path,size_t *size) {
    FILE *f=fopen(path,"rb");
    assert(f);
    uint64_t hash=UINT64_C(14695981039346656037);
    int first=-1,second=-1,last_a=-1,last_b=-1,c=0;
    size_t total=0;
    while((c=fgetc(f))!=EOF) {
        if(total==0)first=c;
        if(total==1)second=c;
        last_a=last_b;last_b=c;
        hash^=(uint8_t)c;
        hash*=UINT64_C(1099511628211);
        total++;
    }
    assert(!ferror(f));
    assert(fclose(f)==0);
    assert(total>500 && first==0xff && second==0xd8);
    assert(last_a==0xff && last_b==0xd9);
    *size=total;
    return hash;
}
static uint64_t pixel_delta(const uint8_t *a,const uint8_t *b,size_t n){
    uint64_t total=0;
    for(size_t i=0;i<n;i++)
       total+=(a[i]>b[i])?a[i]-b[i]:b[i]-a[i];
    return total;
}
int main(int argc,char **argv){
    assert(argc==1||(argc==2&&!strcmp(argv[1],"--keep")));
    const int keep=argc==2;
    for(unsigned y=0;y<H;y++)for(unsigned x=0;x<STRIDE;x++){
        const unsigned v=400u+(((x*1103u+y*773u+((x*y)%17u)*599u)%59100u));
        bayer[(size_t)y*STRIDE+x]=(uint16_t)v;
    }
    memcpy(original,bayer,sizeof(bayer));
    const nx_bayer_calibration cal={
        NX_BAYER_RGGB,{64,64,64,64},{61000,61000,61000,61000},0
    };
    const nx_linear_params params={
        0,65535,1.55f,{1.04f,1.f,.97f},.67f
    };
    char filenames[LOOKS][120];
    uint64_t hashes[LOOKS]={0};
    size_t sizes[LOOKS]={0};
    for(unsigned k=0;k<LOOKS;k++){
        const unsigned film_id=ids[k];
        assert(nx_film_by_id(film_id)!=NULL);
        assert(nx_bayer_prejpeg_film_streaming(
             bayer,H*STRIDE,STRIDE,processed[k],sizeof(processed[k]),
             W*3u,W,H,&cal,&params,film_id)==0);
        assert(memcmp(bayer,original,sizeof(bayer))==0);
        const int n=snprintf(filenames[k],sizeof(filenames[k]),
                      "outputs/nx_film_e2e_%ld_%u.jpg",(long)getpid(),film_id);
        assert(n>0 && (size_t)n<sizeof(filenames[k]));
        assert(access(filenames[k],F_OK)!=0);
        nx_host_jpeg_writer *writer=nx_host_jpeg_writer_create_with_sampling(
                           filenames[k],NULL,0,NX_HOST_JPEG_420);
        assert(writer);
        const nx_bayer_rgb8_sink sink=nx_host_jpeg_writer_sink(writer);
        assert(nx_bayer_prejpeg_emit_rows(bayer,H*STRIDE,STRIDE,
                     W,H,&cal,&params,film_id,&sink)==0);
        nx_host_jpeg_writer_destroy(writer);
        hashes[k]=hash_jpg(filenames[k],&sizes[k]);
        printf("HOST_FILM_JPEG id=%u path=%s bytes=%zu hash=%016llx\n",
             film_id,filenames[k],sizes[k],(unsigned long long)hashes[k]);
    }
    for(unsigned i=0;i<LOOKS;i++)for(unsigned j=i+1;j<LOOKS;j++){
        const uint64_t delta=pixel_delta(processed[i],processed[j],
                                         sizeof(processed[i]));
        assert(delta>1000); /* actual independent pixel transforms, not menu ID */
        assert(hashes[i]!=hashes[j]); /* actual JPEG bitstreams differ */
        printf("HOST_PIXEL_DELTA id=%u vs=%u absolute_rgb_sum=%llu\n",
           ids[i],ids[j],(unsigned long long)delta);
    }
    /* A monochrome rendering must not leave saturated color behind. */
    uint64_t mono_chroma=0;
    for(size_t i=0;i<W*H;i++){
       const unsigned char *p=processed[2]+3u*i;
       mono_chroma+=(p[0]>p[1]?p[0]-p[1]:p[1]-p[0]);
       mono_chroma+=(p[1]>p[2]?p[1]-p[2]:p[2]-p[1]);
    }
    assert(mono_chroma< W*H*4u);
    assert(memcmp(bayer,original,sizeof(bayer))==0);
    for(unsigned k=0;k<LOOKS;k++)if(!keep)assert(unlink(filenames[k])==0);
    /* Original is preserved by producer (no host filter or JPEG injection).
     * User-selected RAW/SRW must never be overwritten by these tests.
     */
    printf("PASS real HOST pixel processing and 3 different JPEG 4:2:0 encodes; RAW untouched; no camera ISP claims\n");
    return 0;
}
