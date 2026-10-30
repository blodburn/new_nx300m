#define _POSIX_C_SOURCE 200809L
#include "nx300m_tizen_film_controller.h"
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static size_t index_for_id(unsigned id){
 const nx_film_preset *p=nx_film_by_id(id);
 if(!p)return 0;
 for(size_t i=0;i<nx_film_count();i++){
  const nx_film_preset *item=nx_film_by_index(i);
  if(item&&item->id==p->id)return i;
 }
 return 0;
}
void nx_tizen_film_controller_init(
 nx_tizen_film_controller *ctrl,unsigned selected_id,
 nx_tizen_film_save_fn save,void *save_user){
 if(!ctrl)return;
 memset(ctrl,0,sizeof(*ctrl));
 const nx_film_preset *preset=nx_film_by_id(selected_id);
 ctrl->committed_id=preset?preset->id:0;
 ctrl->preview_index=index_for_id(ctrl->committed_id);
 ctrl->save=save;
 ctrl->save_user=save_user;
}
int nx_tizen_film_dispatch(
 nx_tizen_film_controller *ctrl,enum nx_tizen_film_event event){
 if(!ctrl||!nx_film_count())return NX_TIZEN_FILM_ERROR;
 switch(event){
 case NX_TIZEN_FILM_OPEN:
  if(ctrl->open)return NX_TIZEN_FILM_NO_CHANGE;
  ctrl->preview_index=index_for_id(ctrl->committed_id);
  ctrl->open=1;
  return NX_TIZEN_FILM_CHANGED;
 case NX_TIZEN_FILM_ROTATE_CW:
 case NX_TIZEN_FILM_ROTATE_CCW:
  if(!ctrl->open)return NX_TIZEN_FILM_NO_CHANGE;
  ctrl->preview_index=(ctrl->preview_index+nx_film_count()+
      (event==NX_TIZEN_FILM_ROTATE_CW?1:nx_film_count()-1))%
      nx_film_count();
  return NX_TIZEN_FILM_CHANGED;
 case NX_TIZEN_FILM_CANCEL:
  if(!ctrl->open)return NX_TIZEN_FILM_NO_CHANGE;
  ctrl->preview_index=index_for_id(ctrl->committed_id);
  ctrl->open=0;
  return NX_TIZEN_FILM_CHANGED;
 case NX_TIZEN_FILM_CONFIRM:{
  if(!ctrl->open)return NX_TIZEN_FILM_NO_CHANGE;
  const nx_film_preset *p=nx_film_by_index(ctrl->preview_index);
  if(!p)return NX_TIZEN_FILM_ERROR;
  if(p->id==ctrl->committed_id){
   ctrl->open=0;
   return NX_TIZEN_FILM_NO_CHANGE;
  }
  /* Fail closed: keep the old active mode and the current preview visible
   * if persistence fails. No early source/shutter state modification. */
  if(!ctrl->save||ctrl->save(ctrl->save_user,p->id)!=0)
   return NX_TIZEN_FILM_ERROR;
  ctrl->committed_id=p->id;
  ctrl->open=0;
  return NX_TIZEN_FILM_SAVED;
 }
 default:return NX_TIZEN_FILM_ERROR;
 }
}
int nx_tizen_film_view_state(const nx_tizen_film_controller *ctrl,
                            nx_tizen_film_view *out){
 if(!ctrl||!out||!nx_film_count())return -1;
 const size_t count=nx_film_count();
 const size_t index=ctrl->open?ctrl->preview_index:
                                     index_for_id(ctrl->committed_id);
 if(index>=count)return -1;
 const nx_film_preset *selected=nx_film_by_index(index);
 const nx_film_preset *before=nx_film_by_index((index+count-1)%count);
 const nx_film_preset *after=nx_film_by_index((index+1)%count);
 if(!selected||!before||!after)return -1;
 *out=(nx_tizen_film_view){
  .committed_id=ctrl->committed_id,
  .preview_id=selected->id,
  .preview_name=selected->name,
  .preview_description=selected->description,
  .preceding_name=before->name,
  .following_name=after->name,
  .preview_index=index,.count=count,
  .open=ctrl->open,
  .dirty=(ctrl->open&&selected->id!=ctrl->committed_id)
 };
 return 0;
}
int nx_tizen_film_save_file(void *path_user,unsigned id){
 const char *path=path_user;
 const nx_film_preset *preset=nx_film_by_id(id);
 if(!preset||!path||!path[0])return -1;
 const size_t n=strlen(path);
 if(n>4096||n>SIZE_MAX-16u)return -1;
 struct stat old;
 if(lstat(path,&old)==0){
  if(!S_ISREG(old.st_mode))return -1; /* refuse symlink, dir and device */
 }else if(errno!=ENOENT)return -1;
 char *tmp=malloc(n+16u);
 if(!tmp)return -1;
 memcpy(tmp,path,n);
 memcpy(tmp+n,".tmp.XXXXXX",12u);
 int fd=mkstemp(tmp);
 if(fd<0){free(tmp);return -1;}
 FILE *stream=fdopen(fd,"wb");
 if(!stream){
  close(fd);
  unlink(tmp);
  free(tmp);
  return -1;
 }
 int ok=0;
 if(fprintf(stream,"NX_FILM_MENU %u\npreset=%u\n",
            NX_FILM_MENU_VERSION,preset->id)<0||
    fflush(stream)!=0||fsync(fd)!=0)ok=-1;
 if(fclose(stream)!=0)ok=-1;
 if(ok==0 && rename(tmp,path)!=0)ok=-1;
 if(ok!=0)unlink(tmp);
 free(tmp);
 return ok;
}
