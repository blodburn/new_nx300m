/* HOST ONLY: generate two valid baseline JPEGs with unchanged synthetic Exif.
 * This never reads any camera JPEG, firmware, sensor data or other private file.
 */
#include "nx300m_host_jpeg_sink.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

enum { WIDTH=34u, HEIGHT=22u };
/* Exif\0\0 + little-endian TIFF, IFD0->ExifIFD->tag 0x927C.
 * The 'NX-MAKER' marker is SYNTHETIC and is NOT a Samsung MakerNote.
 */
static const uint8_t synthetic_app1[]={
 'E','x','i','f',0,0,
 'I','I',42,0,8,0,0,0,  /* TIFF header, first IFD at offset 8 */
 1,0,                   /* IFD0: one ExifIFD tag */
 0x69,0x87,4,0,1,0,0,0,26,0,0,0,
 0,0,0,0,              /* IFD0 next IFD */
 1,0,                  /* ExifIFD: one MakerNote tag */
 0x7c,0x92,7,0,8,0,0,0,44,0,0,0,
 0,0,0,0,              /* ExifIFD next IFD */
 'N','X','-','M','A','K','E','R'
};

static int generate(const char *path,unsigned effect){
 nx_host_jpeg_writer *w=nx_host_jpeg_writer_create_with_sampling(
   path,synthetic_app1,sizeof(synthetic_app1),NX_HOST_JPEG_420);
 if(!w)return -1;
 nx_bayer_rgb8_sink sink=nx_host_jpeg_writer_sink(w);
 uint8_t row[WIDTH*3u];
 int bad=sink.begin(sink.user,WIDTH,HEIGHT,effect)!=0;
 for(unsigned y=0u;y<HEIGHT&&!bad;y++){
  for(unsigned x=0u;x<WIDTH;x++){
   row[x*3u]=(uint8_t)(x*7u+y*5u+(effect?21u:0u));
   row[x*3u+1u]=(uint8_t)(x*3u+y*11u);
   row[x*3u+2u]=(uint8_t)(x*17u+y*2u);
  }
  if(sink.write_row(sink.user,y,row,sizeof(row))!=0)bad=1;
 }
 if(!bad&&sink.commit(sink.user)!=0)bad=1;
 if(bad)sink.abort(sink.user);
 nx_host_jpeg_writer_destroy(w);
 return bad?-1:0;
}
int main(int argc,char **argv){
 if(argc!=3)return 2;
 if(generate(argv[1],0u)!=0||generate(argv[2],1u)!=0)return 1;
 puts("PASS NX300M synthetic baseline JPEG pair, valid TIFF MakerNote tag and 4:2:0");
 return 0;
}
