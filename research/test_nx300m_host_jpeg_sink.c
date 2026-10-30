#define _POSIX_C_SOURCE 200809L
#include "nx300m_host_jpeg_sink.h"
#include "nx300m_film_menu.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
enum {W=33,H=25,STRIDE=W+3};
static uint16_t raw[H*STRIDE],saved[H*STRIDE];
static const uint8_t original_exif[]={
 'E','x','i','f',0,0,'I','I',42,0,8,0,0,0,0,0,0,0,0,0
};
static int read_bytes(const char *name,uint8_t **bytes,size_t *size){
 FILE *fp=fopen(name,"rb");
 if(!fp)return -1;
 if(fseek(fp,0,SEEK_END)!=0){fclose(fp);return -1;}
 long n=ftell(fp);
 if(n<0||fseek(fp,0,SEEK_SET)!=0){fclose(fp);return -1;}
 uint8_t *d=malloc((size_t)n+1u);
 if(!d){fclose(fp);return -1;}
 size_t count=fread(d,1,(size_t)n,fp);
 fclose(fp);
 if(count!=(size_t)n){free(d);return -1;}
 *bytes=d;*size=count;return 0;
}
static int marker_present(const uint8_t *p,size_t size,const uint8_t *needle,
                          size_t count){
 if(count>size)return 0;
 for(size_t j=0;j+count<=size;j++)
  if(!memcmp(p+j,needle,count))return 1;
 return 0;
}
int main(void){
 for(unsigned y=0;y<H;y++)
  for(unsigned x=0;x<STRIDE;x++)
   raw[(size_t)y*STRIDE+x]=(uint16_t)(2500+(x*1500+y*350)%57000u);
 memcpy(saved,raw,sizeof(raw));
 nx_bayer_calibration cal={NX_BAYER_RGGB,{64,64,64,64},
                            {61000,61000,61000,61000},1200};
 nx_linear_params look={0,65535,1.7f,{1.1f,1.f,.95f},.65f};
 char path[128];
 int n=snprintf(path,sizeof(path),"outputs/.nx_jpeg_host_proof_%ld.jpg",
                (long)getpid());
 assert(n>0&&(size_t)n<sizeof(path)&&access(path,F_OK)!=0);
 assert(nx_host_jpeg_writer_create(path,(const uint8_t*)"bad",3)==NULL);
 nx_host_jpeg_writer *w=nx_host_jpeg_writer_create(path,original_exif,
                                                    sizeof(original_exif));
 assert(w);
 nx_bayer_rgb8_sink sink=nx_host_jpeg_writer_sink(w);
 assert(nx_bayer_prejpeg_emit_rows(raw,H*STRIDE,STRIDE,W,H,&cal,&look,103,
                                  &sink)==0);
 nx_host_jpeg_writer_destroy(w);
 uint8_t *jpg=NULL;size_t len=0;
 assert(read_bytes(path,&jpg,&len)==0&&len>200);
 assert(jpg[0]==0xff&&jpg[1]==0xd8);
 assert(jpg[len-2]==0xff&&jpg[len-1]==0xd9);
 /* Exact optional APP1 Exif bytes; do not synthesize camera metadata. */
 assert(marker_present(jpg,len,original_exif,sizeof(original_exif)));
 const uint8_t sof[]={0xff,0xc0,0,17,8,0,H,0,W,3};
 assert(marker_present(jpg,len,sof,sizeof(sof)));
 const uint8_t sos[]={0xff,0xda};
 assert(marker_present(jpg,len,sos,sizeof(sos)));
 assert(!memcmp(raw,saved,sizeof(raw)));
 /* Original never opens file or emits a second JPEG. */
 char original_path[128];
 n=snprintf(original_path,sizeof(original_path),
            "outputs/.nx_jpeg_host_orig_%ld.jpg",(long)getpid());
 assert(n>0&&(size_t)n<sizeof(original_path)&&access(original_path,F_OK)!=0);
 w=nx_host_jpeg_writer_create(original_path,NULL,0);
 assert(w);sink=nx_host_jpeg_writer_sink(w);
 assert(nx_bayer_prejpeg_emit_rows(raw,H*STRIDE,STRIDE,W,H,&cal,&look,0,
                                  &sink)==1);
 nx_host_jpeg_writer_destroy(w);
 assert(access(original_path,F_OK)!=0);
 /* Create-only transaction rejects existing destination without overwriting
  * any already-published JPEG, and abort cleans the staging filename. */
 w=nx_host_jpeg_writer_create(path,NULL,0);
 assert(w);sink=nx_host_jpeg_writer_sink(w);
 assert(nx_bayer_prejpeg_emit_rows(raw,H*STRIDE,STRIDE,W,H,&cal,&look,103,
                                  &sink)==-1);
 nx_host_jpeg_writer_destroy(w);
 uint8_t *again=NULL;size_t len2=0;
 assert(read_bytes(path,&again,&len2)==0&&len2==len);
 assert(!memcmp(jpg,again,len));
 free(jpg);free(again);
 /* Missing folder: fail-closed; no extra partial file emitted. */
 w=nx_host_jpeg_writer_create("outputs/.nonexistent_host_jpeg_dir/fail.jpg",
                             NULL,0);
 assert(w);sink=nx_host_jpeg_writer_sink(w);
 assert(nx_bayer_prejpeg_emit_rows(raw,H*STRIDE,STRIDE,W,H,&cal,&look,103,
                                  &sink)==-1);
 nx_host_jpeg_writer_destroy(w);
 assert(!memcmp(raw,saved,sizeof(raw)));
 printf("PASS HOST baseline JPEG %ux%u, Exif APP1 byte-copy, SOI/SOF/SOS/EOI, original bypass, RAW unchanged, overwrite blocked, invalid destination aborted, file=%s bytes=%zu\n",
        W,H,path,len);
 return 0;
}
