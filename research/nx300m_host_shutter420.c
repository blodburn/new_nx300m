/* Offline route: committed Film Simulator preset -> exactly one still JPEG.
 * The real NX300M shutter callback, native ISP/YCC ownership, RAW writer,
 * JPEG/EXIF and full-brick recovery all remain unverified.
 */
#include "nx300m_host_shutter420.h"
#include "nx300m_film_menu.h"
#include <string.h>

int nx_host_shutter420_save_committed(
    const nx_host_shutter420_request *r,nx_shutter_result *out){
 if(!out)return -1;
 memset(out,0,sizeof(*out));
 if(!r||(r->mode!=NX_SAVE_JPEG_ONLY &&
         r->mode!=NX_SAVE_RAW_AND_JPEG &&
         r->mode!=NX_SAVE_RAW_ONLY))return -1;

 const int with_raw=(r->mode!=NX_SAVE_JPEG_ONLY);
 const int with_jpeg=(r->mode!=NX_SAVE_RAW_ONLY);
 if(with_raw&&(!r->write_raw||!r->opaque_raw||r->raw_bytes==0u))
  return -1;

 unsigned committed=0u;
 if(with_jpeg){
  if(!r->film_controller)return -1;
  const nx_film_preset *p=nx_film_by_id(
      r->film_controller->committed_id);
  if(!p||p->id!=r->film_controller->committed_id)return -1;
  committed=p->id;
  out->selected_film_id=committed;
  if(committed==0u){
   /* In Original mode, do not load film module or re-encode JPEG. */
   if(!r->write_original_jpeg)return -1;
  }else{
   /* Explicit association avoids accidentally applying another preset's
    * LUT, but does not authenticate LUT contents/third-party film names. */
   if(r->lut_preset_id!=committed||!r->copied_film_job||
      !r->freestanding_module_path||!r->freestanding_module_path[0]||
      !r->new_film_jpeg_path||!r->new_film_jpeg_path[0])
    return -1;
  }
 }
 /* The controller's preview_index and open/dirty fields are NEVER read.
  * A pending preview can never change a shutter-capture preset. */

 if(with_raw){
  if(r->write_raw(r->opaque_raw,r->raw_bytes,r->user)!=0)return -1;
  out->raw_saved=1u;
 }
 if(!with_jpeg)return 0;

 if(committed==0u){
  if(r->write_original_jpeg(r->user)!=0)return -1;
  out->jpeg_saved=1u;
  return 0;
 }
 if(nx_host_freestanding420_jpeg_copy(
      r->freestanding_module_path,r->copied_film_job,0,
      r->new_film_jpeg_path,r->original_exif_app1,r->exif_bytes)!=0)
  return -1;

 out->applied_film=1u;
 out->jpeg_saved=1u;
 return 0;
}
