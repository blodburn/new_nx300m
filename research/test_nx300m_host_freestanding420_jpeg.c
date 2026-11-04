#define _POSIX_C_SOURCE 200809L
/* Synthetic host JPEG byte-equivalence regression. NO camera interaction.
 * The independent no-libc DSO is dlopen'd by the host adapter, which is
 * deliberately NOT linked into the actual Samsung camera application.
 */
#include "nx300m_host_freestanding420_jpeg.h"
#include "nx300m_host420_lutgrid_jpeg.h"
#include "nx300m_preview_rgb.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum { W=34,H=22,YS=W+6,CS=W+8 };
static uint8_t yy[H*YS],cc[(H/2u)*CS];
static const uint8_t exif[]={
 'E','x','i','f',0,0,'I','I',42,0,8,0,0,0,0,0,0,0,0,0
};
static void copied_fixture(void){
 memset(yy,0xb7,sizeof(yy));
 memset(cc,0xc9,sizeof(cc));
 for(unsigned y=0;y<H;y++)
  for(unsigned x=0;x<W;x++)
   yy[(size_t)y*YS+x]=(uint8_t)(9u+x*11u+y*23u);
 for(unsigned y=0;y<H/2u;y++)
  for(unsigned x=0;x<W;x++)
   cc[(size_t)y*CS+x]=(uint8_t)(41u+x*17u+y*13u);
}
static nx_rgb12 *make_lut(unsigned n){
 size_t len=(size_t)n*n*n;
 nx_rgb12 *v=malloc(len*sizeof(*v));
 assert(v);
 for(unsigned b=0;b<n;b++)
  for(unsigned g=0;g<n;g++)
   for(unsigned r=0;r<n;r++){
    const size_t k=((size_t)b*n+g)*n+r;
    v[k]=(nx_rgb12){
      (uint16_t)((r*3800u+(n-1u)/2u)/(n-1u)),
      (uint16_t)((g*3700u+(n-1u)/2u)/(n-1u)),
      (uint16_t)((b*3900u+(n-1u)/2u)/(n-1u)),0u
    };
   }
 return v;
}
static int file_exists(const char *p){return access(p,F_OK)==0;}
static void identical_jpeg(const char *a,const char *b,int expect_exif){
 FILE *x=fopen(a,"rb"),*y=fopen(b,"rb");
 assert(x&&y);
 int c0=fgetc(x),c1=fgetc(x);
 assert(c0==255&&c1==216);
 assert(fgetc(y)==c0&&fgetc(y)==c1);
 size_t count=2u;
 int prev1=0,prev2=0,seen_exif=0;
 /* A small rolling signature check is sufficient for a synthetic APP1
  * propagation gate; the exact two JPEG streams must match bytewise. */
 const uint8_t prefix[6]={'E','x','i','f',0,0};
 uint8_t last[6]={0};
 for(;;){
  int u=fgetc(x),v=fgetc(y);
  assert(u==v);
  if(u==EOF)break;
  memmove(last,last+1,5);
  last[5]=(uint8_t)u;
  if(memcmp(last,prefix,6)==0)seen_exif=1;
  prev2=prev1;prev1=u;count++;
 }
 assert(!ferror(x)&&!ferror(y));
 assert(fclose(x)==0&&fclose(y)==0);
 assert(count>300u&&prev2==255&&prev1==217);
 assert(seen_exif==expect_exif);
}
static nx_film_owned420_hypothesis_job new_job(
 unsigned n,unsigned order,nx_rgb12 *lut,nx_preview_processor *p){
 nx_film_owned420_hypothesis_job j={0};
 j.copy_declaration=NX_FILM_420_COPY_DECLARATION;
 j.hypothesis=order;
 j.y=yy;j.y_bytes=sizeof(yy);j.y_stride=YS;
 j.chroma=cc;j.chroma_bytes=sizeof(cc);j.chroma_stride=CS;
 j.width=W;j.height=H;
 j.decode_srgb=p->decode_srgb;j.decode_entries=256u;
 j.encode_srgb=p->encode_srgb;j.encode_entries=4096u;
 j.lut=lut;j.lut_nodes=(size_t)n*n*n;j.grid=n;
 /* The adapter ignores output-buffer metadata and supplies its own 1 row. */
 j.rgb=NULL;j.rgb_bytes=0u;j.rgb_stride=0u;
 return j;
}
static void run_one(const char *module,unsigned n,unsigned order){
 copied_fixture();
 uint8_t saved_y[sizeof(yy)],saved_c[sizeof(cc)];
 memcpy(saved_y,yy,sizeof(yy));memcpy(saved_c,cc,sizeof(cc));
 nx_rgb12 *lut=make_lut(n);
 size_t lut_size=(size_t)n*n*n*sizeof(*lut);
 nx_rgb12 *lut_copy=malloc(lut_size);
 assert(lut_copy);
 memcpy(lut_copy,lut,lut_size);
 nx_preview_processor preview;
 assert(nx_preview_init(&preview)==0);
 nx_film_owned420_hypothesis_job j=new_job(n,order,lut,&preview);
 char result[160],oracle[160];
 assert(snprintf(result,sizeof(result),
    "outputs/strip_jpeg_%ld_%u_%u.jpg",(long)getpid(),n,order)>0);
 assert(snprintf(oracle,sizeof(oracle),
    "outputs/strip_jpeg_ref_%ld_%u_%u.jpg",(long)getpid(),n,order)>0);
 assert(!file_exists(result)&&!file_exists(oracle));
 const int include_exif=(n==65u);
 const uint8_t *app1=include_exif?exif:NULL;
 const size_t exif_len=include_exif?sizeof(exif):0u;
 assert(nx_host_freestanding420_jpeg_copy(module,&j,0,result,app1,
                                         exif_len)==0);
 assert(nx_host420_lutgrid_jpeg_hypothesis(
    yy,sizeof(yy),YS,cc,sizeof(cc),CS,W,H,
    order==NX_FILM_BT601_FULL_CBCR_HYPOTHESIS?
      NX_HOST420_CBCR_EXPERIMENTAL:NX_HOST420_CRCB_EXPERIMENTAL,
    NX_420_BT601_FULL,lut,n,0,oracle,app1,exif_len)==0);
 identical_jpeg(result,oracle,include_exif);
 /* Output create-only: second attempt must fail, not replace content. */
 assert(nx_host_freestanding420_jpeg_copy(module,&j,0,result,app1,
                                         exif_len)==-1);
 identical_jpeg(result,oracle,include_exif);
 assert(memcmp(saved_y,yy,sizeof(yy))==0);
 assert(memcmp(saved_c,cc,sizeof(cc))==0);
 assert(memcmp(lut_copy,lut,lut_size)==0);
 assert(unlink(result)==0&&unlink(oracle)==0);
 free(lut_copy);free(lut);
 printf("PASS host row-strip JPEG: LUT=%u order=%u, byte-equal "
        "4:2:0, EXIF=%d, no-overwrite, immutable inputs\n",
        n,order,include_exif);
}
static void reject_cases(const char *module){
 copied_fixture();
 nx_rgb12 *lut=make_lut(18u);
 nx_preview_processor preview;
 assert(nx_preview_init(&preview)==0);
 nx_film_owned420_hypothesis_job j=new_job(
    18u,NX_FILM_BT601_FULL_CBCR_HYPOTHESIS,lut,&preview);
 char path[160];
 assert(snprintf(path,sizeof(path),"outputs/strip_reject_%ld.jpg",
                 (long)getpid())>0);
 assert(!file_exists(path));
 /* Original bypass is unconditional: never open the DSO or JPEG file. */
 assert(nx_host_freestanding420_jpeg_copy(
    NULL,NULL,1,path,NULL,0)==1);
 assert(!file_exists(path));
 nx_film_owned420_hypothesis_job bad=j;
 bad.y_bytes=YS;
 assert(nx_host_freestanding420_jpeg_copy(
    module,&bad,0,path,NULL,0)==-1);
 bad=j;bad.hypothesis=0u;
 assert(nx_host_freestanding420_jpeg_copy(
    module,&bad,0,path,NULL,0)==-1);
 bad=j;bad.lut_nodes=2u;
 assert(nx_host_freestanding420_jpeg_copy(
    module,&bad,0,path,NULL,0)==-1);
 bad=j;bad.width=W-1u;
 assert(nx_host_freestanding420_jpeg_copy(
    module,&bad,0,path,NULL,0)==-1);
 assert(nx_host_freestanding420_jpeg_copy(
    "not_a_freestanding_library.so",&j,0,path,NULL,0)==-1);
 const uint8_t forged_exif[6]={'N','o','t','E','x','i'};
 assert(nx_host_freestanding420_jpeg_copy(
    module,&j,0,path,forged_exif,sizeof(forged_exif))==-1);
 assert(!file_exists(path));
 free(lut);
 puts("PASS host strip JPEG fail closed: Original, metadata, module, EXIF");
}
int main(int argc,char **argv){
 assert(argc==2&&argv[1]);
 for(unsigned n=2u;n<=65u;n=n==2u?18u:n==18u?65u:66u)
  for(unsigned order=1u;order<=2u;order++)
   run_one(argv[1],n,order);
 reject_cases(argv[1]);
 puts("PASS NX300M independent GLIBC-free row -> transactional host JPEG+APP1 EXIF; NO camera integration");
 return 0;
}
