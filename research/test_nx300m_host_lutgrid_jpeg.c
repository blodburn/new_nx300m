#define _POSIX_C_SOURCE 200809L
#include "nx300m_host_lutgrid_jpeg.h"
#include "nx300m_host_jpeg_sink.h"
#include "nx300m_preview_rgb.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum { W=28,H=20,STRIDE=W*3u+7u };
static uint8_t input[H][STRIDE], original[H][STRIDE];
static const uint8_t app1[]={'E','x','i','f',0,0,'I','I',42,0,8,0,0,0,0,0,0,0,0,0};
static nx_rgb12 *new_grid(unsigned n,int inverted){
 nx_rgb12 *lut=malloc((size_t)n*n*n*sizeof(*lut));assert(lut);
 for(unsigned b=0;b<n;b++)for(unsigned g=0;g<n;g++)
 for(unsigned r=0;r<n;r++){
  nx_rgb12 *v=&lut[((size_t)b*n+g)*n+r];
  unsigned rr=(r*4095u+(n-1u)/2u)/(n-1u);
  unsigned gg=(g*4095u+(n-1u)/2u)/(n-1u);
  unsigned bb=(b*4095u+(n-1u)/2u)/(n-1u);
  v->r=(uint16_t)(inverted?4095u-rr:rr);
  v->g=(uint16_t)(inverted?4095u-gg:gg);
  v->b=(uint16_t)(inverted?4095u-bb:bb);
  v->reserved=0;
 }
 return lut;
}
static uint64_t jpeg_hash(const char *path,int *has_exif){
 FILE *f=fopen(path,"rb");assert(f);
 uint64_t sum=UINT64_C(14695981039346656037);
 unsigned char win[sizeof(app1)]={0};
 int first=-1,second=-1,last=-1,prev=-1;
 size_t count=0;
 *has_exif=0;
 for(int v;(v=fgetc(f))!=EOF;){
  if(!count)first=v;
  if(count==1)second=v;
  memmove(win,win+1,sizeof(win)-1);
  win[sizeof(win)-1]=(uint8_t)v;
  if(count+1>=sizeof(win)&&memcmp(win,app1,sizeof(win))==0)*has_exif=1;
  prev=last;last=v;
  sum^=(unsigned)v;sum*=UINT64_C(1099511628211);
  count++;
 }
 assert(!ferror(f)&&fclose(f)==0);
 assert(count>350&&first==255&&second==216&&prev==255&&last==217);
 return sum;
}
static uint64_t expected(const char *path,const nx_rgb12 *lut,unsigned n){
 nx_preview_processor p;assert(nx_preview_init(&p)==0);
 nx_host_jpeg_writer *writer=nx_host_jpeg_writer_create_with_sampling(
    path,app1,sizeof(app1),NX_HOST_JPEG_420);
 assert(writer);
 nx_bayer_rgb8_sink sink=nx_host_jpeg_writer_sink(writer);
 assert(sink.begin(sink.user,W,H,1)==0);
 uint8_t row[W*3u];
 for(unsigned y=0;y<H;y++){
  for(unsigned x=0;x<W;x++){
   const uint8_t *v=input[y]+3u*x;
   nx_rgb12 in={p.decode_srgb[v[0]],p.decode_srgb[v[1]],
                p.decode_srgb[v[2]],0},out;
   assert(nx_lut_grid_host_apply(lut,n,&in,&out,1)==0);
   row[3u*x]=p.encode_srgb[out.r];
   row[3u*x+1]=p.encode_srgb[out.g];
   row[3u*x+2]=p.encode_srgb[out.b];
  }
  assert(sink.write_row(sink.user,y,row,sizeof(row))==0);
 }
 assert(sink.commit(sink.user)==0);
 nx_host_jpeg_writer_destroy(writer);
 int got_exif=0;uint64_t sum=jpeg_hash(path,&got_exif);
 assert(got_exif&&unlink(path)==0);
 return sum;
}
int main(int argc,char **argv){
 for(unsigned y=0;y<H;y++)for(unsigned x=0;x<W;x++){
  input[y][3u*x]=(uint8_t)((x*17u+y*7u)%256u);
  input[y][3u*x+1u]=(uint8_t)((x*7u+y*19u)%256u);
  input[y][3u*x+2u]=(uint8_t)((x*23u+y*3u)%256u);
 }
 for(unsigned y=0;y<H;y++)for(unsigned x=W*3u;x<STRIDE;x++)input[y][x]=0xA5u;
 memcpy(original,input,sizeof(original));
 if(argc==3){
  assert(strcmp(argv[1],"65")==0);
  const size_t count=65u*65u*65u;
  nx_rgb12 *external=malloc(count*sizeof(*external));assert(external);
  assert(nx_lut_grid_host_load(argv[2],65u,external,count)==0);
  char path[160];
  assert(snprintf(path,sizeof(path),
          "outputs/nx_spektrafilm_real_lut_jpeg_%ld.jpg",(long)getpid())>0);
  assert(access(path,F_OK)!=0);
  assert(nx_host_rgb888_lutgrid_jpeg(&input[0][0],sizeof(input),STRIDE,
         W,H,external,65u,0,path,app1,sizeof(app1))==0);
  int exif=0;
  (void)jpeg_hash(path,&exif);
  assert(exif&&unlink(path)==0);
  assert(memcmp(input,original,sizeof(input))==0);
  free(external);
  puts("PASS real SpektraFilm ephemeral 65^3 RGB12 LUT -> host RGB888 JPEG with EXIF and original input unchanged");
  return 0;
 }
 assert(argc==1);
 uint64_t hashes[2];
 for(unsigned t=0;t<2;t++){
  const unsigned n=t?18u:65u;
  nx_rgb12 *lut=new_grid(n,t==0);
  char path[128],oracle[128];
  assert(snprintf(path,sizeof(path),"outputs/nx_grid_jpeg_%ld_%u.jpg",
                  (long)getpid(),n)>0);
  assert(snprintf(oracle,sizeof(oracle),"outputs/nx_grid_jpeg_oracle_%ld_%u.jpg",
                  (long)getpid(),n)>0);
  assert(access(path,F_OK)!=0&&access(oracle,F_OK)!=0);
  assert(nx_host_rgb888_lutgrid_jpeg(&input[0][0],sizeof(input),STRIDE,
       W,H,lut,n,0,path,app1,sizeof(app1))==0);
  int exif=0;
  hashes[t]=jpeg_hash(path,&exif);
  assert(exif&&hashes[t]==expected(oracle,lut,n));
  assert(memcmp(input,original,sizeof(input))==0);
  assert(nx_host_rgb888_lutgrid_jpeg(&input[0][0],sizeof(input),STRIDE,
       W,H,lut,n,0,path,app1,sizeof(app1))==-1);
  assert(jpeg_hash(path,&exif)==hashes[t]);
  assert(unlink(path)==0);
  free(lut);
 }
 assert(hashes[0]!=hashes[1]);
 nx_rgb12 *lut=new_grid(65u,1);
 const char *missing="outputs/nx_grid_jpeg_bypass_no_publish.jpg";
 assert(access(missing,F_OK)!=0);
 assert(nx_host_rgb888_lutgrid_jpeg(&input[0][0],sizeof(input),STRIDE,
       W,H,lut,65,1,missing,NULL,0)==1);
 assert(access(missing,F_OK)!=0);
 assert(nx_host_rgb888_lutgrid_jpeg(&input[0][0],sizeof(input)-STRIDE,
       STRIDE,W,H,lut,65,0,missing,NULL,0)==-1);
 assert(nx_host_rgb888_lutgrid_jpeg(&input[0][0],sizeof(input),STRIDE,
       W,H,lut,0,0,missing,NULL,0)==-1);
 assert(nx_host_rgb888_lutgrid_jpeg(&input[0][0],sizeof(input),STRIDE,
       W,H,NULL,65,0,missing,NULL,0)==-1);
 const uint8_t invalid_exif[]={'B','A','D'};
 assert(nx_host_rgb888_lutgrid_jpeg(&input[0][0],sizeof(input),STRIDE,
       W,H,lut,65,0,missing,invalid_exif,sizeof(invalid_exif))==-1);
 assert(access(missing,F_OK)!=0);
 assert(memcmp(input,original,sizeof(input))==0);
 free(lut);
 puts("PASS NX65/18 independent host RGB888 LUT->JPEG 420: exact oracle, EXIF, source immutable, create-only, Original bypass, error gates");
 return 0;
}
