/* Offline boundary ONLY. This host wrapper loads an independent no-libc
 * math DSO and sends one RGB888 row at a time to the existing host JPEG
 * writer. It does not load on NX300M or use Samsung JPEG/EXIF internals.
 */
#include "nx300m_host_freestanding420_jpeg.h"
#include "nx300m_host_owned420_snapshot.h"
#include "nx300m_host_jpeg_sink.h"
#include <dlfcn.h>
#include <stdint.h>
#include <stdlib.h>

typedef int (*nx_render_row_fn)(const nx_film_owned420_hypothesis_job *,
                                unsigned,unsigned);

int nx_host_freestanding420_jpeg_copy(
    const char *module_path,
    const nx_film_owned420_hypothesis_job *copied_input,
    int original_bypass,
    const char *new_jpeg_path,
    const uint8_t *original_exif_app1,
    size_t exif_bytes){
 /* Original must never pass through any color conversion or host encoder. */
 if(original_bypass)return 1;
 if(!module_path||!module_path[0]||!copied_input||
    !new_jpeg_path||!new_jpeg_path[0]||
    copied_input->width<4u||copied_input->width>8192u||
    copied_input->height<4u||copied_input->height>8192u||
    (copied_input->width&1u)||(copied_input->height&1u))
  return -1;

 /* Detach every subsequently-read Y/C/LUT/transfer-table byte from the
  * caller before starting JPEG output. This is HOST memory only, never
  * proof of live camera DMA ownership or buffer coherency. */
 nx_host_owned420_snapshot snapshot={0};
 if(nx_host_owned420_snapshot_take(&snapshot,copied_input)!=0)return -1;
 const size_t row_bytes=(size_t)copied_input->width*3u;
 uint8_t *row=malloc(row_bytes);
 if(!row){nx_host_owned420_snapshot_release(&snapshot);return -1;}
 int result=-1;
 void *module=dlopen(module_path,RTLD_NOW|RTLD_LOCAL);
 if(!module)goto cleanup_row;
 nx_render_row_fn render=(nx_render_row_fn)
    dlsym(module,"nx_film_core_render_owned420_rows_hypothesis");
 if(!render)goto cleanup_module;

 nx_film_owned420_hypothesis_job job=snapshot.job;
 job.rgb=row;
 job.rgb_bytes=row_bytes;
 job.rgb_stride=row_bytes;
 /* Preflight must reject invalid copy metadata before a JPEG temp is made.
  * The first row is computed and retained for the first sink write. */
 if(render(&job,0u,1u)!=0)goto cleanup_module;

 nx_host_jpeg_writer *writer=nx_host_jpeg_writer_create_with_sampling(
        new_jpeg_path,original_exif_app1,exif_bytes,NX_HOST_JPEG_420);
 if(!writer)goto cleanup_module;
 nx_bayer_rgb8_sink sink=nx_host_jpeg_writer_sink(writer);
 int bad=sink.begin(sink.user,job.width,job.height,1u)!=0;
 if(!bad&&sink.write_row(sink.user,0u,row,row_bytes)!=0)bad=1;
 for(unsigned y=1u;y<job.height&&!bad;y++){
  if(render(&job,y,1u)!=0||
     sink.write_row(sink.user,y,row,row_bytes)!=0)bad=1;
 }
 if(!bad&&sink.commit(sink.user)!=0)bad=1;
 if(bad)sink.abort(sink.user);
 nx_host_jpeg_writer_destroy(writer);
 result=bad?-1:0;

cleanup_module:
 (void)dlclose(module);
cleanup_row:
 free(row);
 nx_host_owned420_snapshot_release(&snapshot);
 return result;
}
