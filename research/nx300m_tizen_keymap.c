#include "nx300m_tizen_keymap.h"
#include <string.h>

/* No locale dependence, whitespace, path characters or log escape control. */
int nx_tizen_keyname_observable(const char *keyname){
 if(!keyname)return 0;
 for(size_t n=0;n<NX_TIZEN_KEYNAME_MAX;n++){
  unsigned char c=(unsigned char)keyname[n];
  if(c==0)return n>0;
  if((c>='A'&&c<='Z')||(c>='a'&&c<='z')||
     (c>='0'&&c<='9')||c=='_'||c=='-'||c=='+')
   continue;
  return 0;
 }
 return 0;
}
int nx_tizen_keymap_set(nx_tizen_keymap *m,const char *cw,
                        const char *ccw,const char *confirm,
                        const char *cancel){
 if(!m)return -1;
 /* Reject any attempt to leave a previous key mapping enabled. */
 memset(m,0,sizeof(*m));
 const char *fields[4]={cw,ccw,confirm,cancel};
 for(unsigned i=0;i<4;i++){
  if(!nx_tizen_keyname_observable(fields[i]))return -1;
  for(unsigned j=0;j<i;j++)
   if(strcmp(fields[i],fields[j])==0)return -1;
 }
 strcpy(m->cw,cw);strcpy(m->ccw,ccw);
 strcpy(m->confirm,confirm);strcpy(m->cancel,cancel);
 m->enabled=1;
 return 0;
}
void nx_tizen_keymap_demo(nx_tizen_keymap *m){
 if(m)(void)nx_tizen_keymap_set(m,"Right","Left","Return","Escape");
}
enum nx_tizen_input nx_tizen_keymap_lookup(
 const nx_tizen_keymap *m,const char *keyname){
 if(!m||!m->enabled||!nx_tizen_keyname_observable(keyname))
  return NX_TIZEN_INPUT_NONE;
 if(strcmp(keyname,m->cw)==0)return NX_TIZEN_INPUT_CW;
 if(strcmp(keyname,m->ccw)==0)return NX_TIZEN_INPUT_CCW;
 if(strcmp(keyname,m->confirm)==0)return NX_TIZEN_INPUT_CONFIRM;
 if(strcmp(keyname,m->cancel)==0)return NX_TIZEN_INPUT_CANCEL;
 return NX_TIZEN_INPUT_NONE;
}
