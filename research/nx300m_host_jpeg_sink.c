#define _POSIX_C_SOURCE 200809L
#include "nx300m_host_jpeg_sink.h"
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <limits.h>
#include <unistd.h>
#include <errno.h>

/* Host-only self-contained ISO/IEC 10918-1 baseline sequential JPEG encoder.
 * Grayscale/sRGB-compatible RGB input -> YCbCr 4:4:4 JPEG, Q=85.
 * Uniform canonical Huffman lengths (not compression-optimal, but compliant).
 * The native Samsung 1.14 encoder's hardware 4:2:0 DMA cannot use this ABI.
 */
enum { MCU=8, COMPONENTS=3 };
typedef struct {uint16_t code;uint8_t len;} hcode;
typedef struct {hcode symbols[256];uint8_t counts[16];uint8_t values[162];unsigned used;} htable;
struct nx_host_jpeg_writer {
 char *destination,*staging_path;
 const uint8_t *exif;size_t exif_size;
 FILE *f;
 uint8_t *scanlines;
 unsigned width,height,row_count;
 uint32_t bitbuf;
 unsigned bitcount;
 int previous_dc[3];
 uint8_t quant[2][64];
 double cos_table[8][8];
 htable dc[2],ac[2];
 int active,committed,failed;
};
static const uint8_t zigzag[64]={
 0,1,8,16,9,2,3,10,17,24,32,25,18,11,4,5,
 12,19,26,33,40,48,41,34,27,20,13,6,7,14,21,28,35,
 42,49,56,57,50,43,36,29,22,15,23,30,37,44,51,58,59,
 52,45,38,31,39,46,53,60,61,54,47,55,62,63};
static const uint8_t qlum[64]={
 16,11,10,16,24,40,51,61,
 12,12,14,19,26,58,60,55,
 14,13,16,24,40,57,69,56,
 14,17,22,29,51,87,80,62,
 18,22,37,56,68,109,103,77,
 24,35,55,64,81,104,113,92,
 49,64,78,87,103,121,120,101,
 72,92,95,98,112,100,103,99};
static const uint8_t qchrom[64]={
 17,18,24,47,99,99,99,99,
 18,21,26,66,99,99,99,99,
 24,26,56,99,99,99,99,99,
 47,66,99,99,99,99,99,99,
 99,99,99,99,99,99,99,99,
 99,99,99,99,99,99,99,99,
 99,99,99,99,99,99,99,99,
 99,99,99,99,99,99,99,99};
static int byte(nx_host_jpeg_writer *w,unsigned value){
 return fputc((int)(value&255u),w->f)!=EOF?0:-1;
}
static int marker(nx_host_jpeg_writer *w,unsigned type){
 return byte(w,0xffu)||byte(w,type)?-1:0;
}
static int be16(nx_host_jpeg_writer *w,unsigned value){
 return byte(w,value>>8)||byte(w,value&255u)?-1:0;
}
static int bytes(nx_host_jpeg_writer *w,const void *b,size_t n){
 return n&&fwrite(b,1,n,w->f)!=n?-1:0;
}
static void table_init(htable *h,int is_ac){
 memset(h,0,sizeof(*h));
 if(is_ac){
  h->counts[7]=162;
  h->values[0]=0x00; /* EOB */
  h->values[1]=0xf0; /* ZRL */
  for(unsigned run=0;run<16;run++)
   for(unsigned size=1;size<=10;size++)
    h->values[2+run*10+size-1]=(uint8_t)(run*16+size);
  h->used=162;
 }else{
  h->counts[3]=12; /* DC symbols for category 0..11 */
  for(unsigned i=0;i<12;i++)h->values[i]=(uint8_t)i;
  h->used=12;
 }
 unsigned index=0,code=0;
 for(unsigned len=1;len<=16;len++){
  for(unsigned j=0;j<h->counts[len-1];j++){
   hcode *a=&h->symbols[h->values[index++]];
   a->code=(uint16_t)code++;
   a->len=(uint8_t)len;
  }
  code<<=1;
 }
}
static int headers(nx_host_jpeg_writer *w){
 static const uint8_t jfif[]={ 'J','F','I','F',0,1,1,0,0,1,0,1,0,0 };
 if(marker(w,0xd8)||marker(w,0xe0)||be16(w,16)||bytes(w,jfif,sizeof(jfif)))
  return -1;
 if(w->exif_size){
  if(marker(w,0xe1)||be16(w,(unsigned)w->exif_size+2u)||
     bytes(w,w->exif,w->exif_size))return -1;
 }
 for(unsigned t=0;t<2;t++){
  if(marker(w,0xdb)||be16(w,67)||byte(w,t))return -1;
  for(unsigned i=0;i<64;i++)
   if(byte(w,w->quant[t][zigzag[i]]))return -1;
 }
 /* 3-component baseline SOF0, 4:4:4 sampling, NOT Samsung native. */
 if(marker(w,0xc0)||be16(w,17)||byte(w,8)||be16(w,w->height)||
    be16(w,w->width)||byte(w,3))return -1;
 for(unsigned c=0;c<3;c++)
  if(byte(w,c+1)||byte(w,0x11)||byte(w,c==0?0:1))return -1;
 for(unsigned kind=0;kind<2;kind++)for(unsigned t=0;t<2;t++){
  const htable *h=kind?&w->ac[t]:&w->dc[t];
  if(marker(w,0xc4)||be16(w,19+h->used)||byte(w,(kind<<4)|t)||
     bytes(w,h->counts,16)||bytes(w,h->values,h->used))return -1;
 }
 if(marker(w,0xda)||be16(w,12)||byte(w,3))return -1;
 for(unsigned c=0;c<3;c++)
  if(byte(w,c+1)||byte(w,c==0?0x00:0x11))return -1;
 return byte(w,0)||byte(w,63)||byte(w,0)?-1:0;
}
static int bits(nx_host_jpeg_writer *w,unsigned value,unsigned n){
 for(unsigned i=n;i>0;i--){
  w->bitbuf=(w->bitbuf<<1)|((value>>(i-1))&1u);
  if(++w->bitcount==8){
   unsigned b=w->bitbuf&255u;
   if(byte(w,b)|| (b==255u&&byte(w,0)))return -1;
   w->bitcount=0;
   w->bitbuf=0;
  }
 }
 return 0;
}
static int huffman(nx_host_jpeg_writer *w,htable *h,unsigned sym){
 hcode hcode=h->symbols[sym&255u];
 return !hcode.len?-1:bits(w,hcode.code,hcode.len);
}
static unsigned category(int n){
 unsigned magnitude=(unsigned)(n<0?-n:n),c=0;
 while(magnitude){c++;magnitude>>=1;}
 return c;
}
static unsigned amplitude(int n,unsigned cat){
 return (unsigned)(n<0?n+(int)((1u<<cat)-1u):n);
}
static int emit_block(nx_host_jpeg_writer *w,int component,
                      double block[8][8]){
 double horizontal[8][8],coeff[64];
 const uint8_t *q=w->quant[component?1:0];
 for(unsigned y=0;y<8;y++)for(unsigned u=0;u<8;u++){
  double acc=0.0;
  for(unsigned x=0;x<8;x++)
   acc+=block[y][x]*w->cos_table[x][u];
  horizontal[y][u]=acc;
 }
 for(unsigned v=0;v<8;v++)for(unsigned u=0;u<8;u++){
  double acc=0.;
  for(unsigned y=0;y<8;y++)
   acc+=horizontal[y][u]*w->cos_table[y][v];
  double factor=(u==0?0.7071067811865475:1.)*
                (v==0?0.7071067811865475:1.)*0.25;
  coeff[v*8+u]=factor*acc/q[v*8+u];
 }
 int ints[64];
 for(unsigned i=0;i<64;i++){
  double c=coeff[i];
  if(c>(double)INT_MAX||c<(double)INT_MIN)return -1;
  ints[i]=(int)lrint(c);
 }
 const int diff=ints[0]-w->previous_dc[component];
 w->previous_dc[component]=ints[0];
 const unsigned dc_cat=category(diff);
 if(dc_cat>11)return -1;
 if(huffman(w,&w->dc[component?1:0],dc_cat)||
    bits(w,amplitude(diff,dc_cat),dc_cat))return -1;
 unsigned run=0;
 for(unsigned i=1;i<64;i++){
  int a=ints[zigzag[i]];
  if(!a){run++;continue;}
  while(run>=16){
   if(huffman(w,&w->ac[component?1:0],0xf0))return -1;
   run-=16;
  }
  unsigned cat=category(a);
  if(cat>10)return -1;
  if(huffman(w,&w->ac[component?1:0],(run<<4)|cat)||
     bits(w,amplitude(a,cat),cat))return -1;
  run=0;
 }
 return run&&huffman(w,&w->ac[component?1:0],0x00)?-1:0;
}
static int encode_rows(nx_host_jpeg_writer *w,unsigned valid_rows){
 for(unsigned left=0;left<w->width;left+=8){
  double block[3][8][8];
  for(unsigned y=0;y<8;y++){
   const unsigned yy=y<valid_rows?y:valid_rows-1;
   const uint8_t *r=w->scanlines+(size_t)yy*w->width*3u;
   for(unsigned x=0;x<8;x++){
    const unsigned xx=left+x<w->width?left+x:w->width-1u;
    const double red=r[3u*xx],green=r[3u*xx+1],blue=r[3u*xx+2];
    block[0][y][x]=0.299*red+0.587*green+0.114*blue-128.;
    block[1][y][x]=-0.168736*red-0.331264*green+0.5*blue;
    block[2][y][x]=0.5*red-0.418688*green-0.081312*blue;
   }
  }
  for(unsigned c=0;c<3;c++)
   if(emit_block(w,(int)c,block[c]))return -1;
 }
 return 0;
}
static void discard(nx_host_jpeg_writer *w){
 if(!w)return;
 if(w->f){fclose(w->f);w->f=NULL;}
 if(w->staging_path){unlink(w->staging_path);}
 w->active=0;
 w->failed=1;
}
static int start(void *user,unsigned width,unsigned height,unsigned film_id){
 nx_host_jpeg_writer *w=user;
 (void)film_id;
 if(!w||w->active||w->committed||!width||!height||width>8192||height>8192)
  return -1;
 w->width=width;w->height=height;
 w->row_count=0;w->bitbuf=0;w->bitcount=0;
 memset(w->previous_dc,0,sizeof(w->previous_dc));
 const size_t row_bytes=(size_t)width*3u;
 w->scanlines=malloc(row_bytes*8u);
 if(!w->scanlines)return -1;
 size_t pathlen=strlen(w->destination);
 if(pathlen>4096 || pathlen>SIZE_MAX-16)return -1;
 w->staging_path=malloc(pathlen+16);
 if(!w->staging_path)return -1;
 memcpy(w->staging_path,w->destination,pathlen);
 memcpy(w->staging_path+pathlen,".tmp.XXXXXX",12);
 int fd=mkstemp(w->staging_path);
 if(fd<0)return -1;
 w->f=fdopen(fd,"wb");
 if(!w->f){close(fd);return -1;}
 w->active=1;
 for(unsigned i=0;i<64;i++){
  unsigned lum=(unsigned)((qlum[i]*30u+50u)/100u);
  unsigned chr=(unsigned)((qchrom[i]*30u+50u)/100u);
  w->quant[0][i]=(uint8_t)(lum?lum:1);
  w->quant[1][i]=(uint8_t)(chr?chr:1);
 }
 for(unsigned x=0;x<8;x++)for(unsigned u=0;u<8;u++)
  w->cos_table[x][u]=cos(((2.0*x+1.0)*u)*3.14159265358979323846/16.0);
 for(unsigned i=0;i<2;i++){
  table_init(&w->dc[i],0);table_init(&w->ac[i],1);
 }
 return headers(w);
}
static int row(void *user,unsigned y,const uint8_t *rgb,size_t len){
 nx_host_jpeg_writer *w=user;
 if(!w||!w->active||!w->f||!rgb||y!=w->row_count||
    len!=(size_t)w->width*3u)return -1;
 memcpy(w->scanlines+(size_t)(y%8u)*len,rgb,len);
 w->row_count++;
 if(w->row_count%8u==0&&encode_rows(w,8u))return -1;
 return 0;
}
static int finish(void *user){
 nx_host_jpeg_writer *w=user;
 if(!w||!w->active||!w->f||w->row_count!=w->height)return -1;
 const unsigned rem=w->row_count%8u;
 if(rem&&encode_rows(w,rem))return -1;
 if(w->bitcount){
  unsigned remaining=8u-w->bitcount;
  if(bits(w,(1u<<remaining)-1u,remaining))return -1;
 }
 if(marker(w,0xd9)||fflush(w->f)||fsync(fileno(w->f)))return -1;
 if(fclose(w->f)!=0){w->f=NULL;return -1;}
 w->f=NULL;
 /* Create-only publish: hard-link succeeds atomically on same filesystem,
  * and fails without touching a pre-existing JPEG. Never replace a file. */
 if(link(w->staging_path,w->destination)!=0)return -1;
 unlink(w->staging_path);
 w->active=0;w->committed=1;
 return 0;
}
static void abort_image(void *user){discard((nx_host_jpeg_writer*)user);}
nx_host_jpeg_writer *nx_host_jpeg_writer_create(
 const char *destination,const uint8_t *original_exif_app1,size_t exif_bytes){
 if(!destination||!destination[0]||strlen(destination)>4096||
    ((exif_bytes>0)&&(!original_exif_app1||exif_bytes<6||
                      exif_bytes>65533u||
                      memcmp(original_exif_app1,"Exif\0\0",6)!=0)))
  return NULL;
 nx_host_jpeg_writer *w=calloc(1,sizeof(*w));
 if(!w)return NULL;
 w->destination=strdup(destination);
 if(!w->destination){free(w);return NULL;}
 w->exif=original_exif_app1;
 w->exif_size=exif_bytes;
 return w;
}
nx_bayer_rgb8_sink nx_host_jpeg_writer_sink(nx_host_jpeg_writer *w){
 nx_bayer_rgb8_sink cb={start,row,finish,abort_image,w};
 return cb;
}
void nx_host_jpeg_writer_destroy(nx_host_jpeg_writer *w){
 if(!w)return;
 discard(w);
 free(w->destination);free(w->staging_path);free(w->scanlines);free(w);
}
