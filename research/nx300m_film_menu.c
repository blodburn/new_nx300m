#include "nx300m_film_menu.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#define MIX(RG,GB,BR) {1.f-(RG),RG,0.f,0.f,1.f-(GB),GB,(BR),0.f,1.f-(BR)}
/* Single Leica Q3 research reference only (Q2 dropped). The following five Q3 study coefficients are independent placeholders, NOT extracted/measured Leica firmware values. */
static const nx_film_preset PRESETS[] = {
 {0,0,"Samsung Original","Neutral reference",1.00f,0.f,0.f,1.f,{1,0,0,0,1,0,0,0,1}},
 {100,1,"Fuji PROVIA Study","Neutral color baseline",1.04f,0.01f,-0.01f,0.99f,{1,0,0,0,1,0,0,0,1}},
 {101,1,"Fuji Velvia Study","Punchier colors",1.24f,-0.08f,-0.03f,0.94f,MIX(.025f,.030f,.018f)},
 {102,1,"Fuji ASTIA Study","Softer tones",1.08f,.060f,-.035f,1.03f,MIX(.018f,.020f,.005f)},
 {103,1,"Fuji Classic Chrome Study","Muted cool tone",.76f,-.045f,-.030f,1.06f,MIX(.040f,.010f,.020f)},
 {104,1,"Fuji Classic Negative Study","Deep contrast color",.89f,-.13f,-.06f,.91f,MIX(.008f,.025f,.030f)},
 {105,1,"Fuji ETERNA Study","Soft cinematic tone",.72f,.08f,-.04f,1.04f,MIX(.014f,.028f,.018f)},
 {106,1,"Fuji ACROS Study","Black and white",0.f,-.08f,-.01f,.92f,{1,0,0,0,1,0,0,0,1}},
 {200,2,"leica-standard","Q3 reference: neutral study",1.f,0.f,0.f,1.f,{1,0,0,0,1,0,0,0,1}},
 {201,2,"leica-vivid","Q3 reference: vivid study",1.2f,-.045f,-.035f,.945f,MIX(.020f,.018f,.010f)},
 {202,2,"leica-natural","Q3 reference: natural study",.82f,.045f,.02f,1.035f,MIX(.009f,.015f,.008f)},
 {203,2,"leica-monochrome","Q3 reference: monochrome study",0.f,.02f,0.f,1.f,{1,0,0,0,1,0,0,0,1}},
 {204,2,"leica-monochrome-hc","Q3 reference: high-contrast mono study",0.f,-.16f,-.10f,.9f,{1,0,0,0,1,0,0,0,1}},
};
static unsigned canonical_id(unsigned id){return (id>=300 && id<=304)?id-100:id;}
size_t nx_film_count(void){return sizeof(PRESETS)/sizeof(PRESETS[0]);}
const nx_film_preset *nx_film_by_index(size_t i){return i<nx_film_count()?&PRESETS[i]:NULL;}
const nx_film_preset *nx_film_by_id(unsigned id){
    id=canonical_id(id);
    for(size_t i=0;i<nx_film_count();i++) if(PRESETS[i].id==id)return &PRESETS[i];
    return NULL;
}
void nx_film_menu_init(nx_film_menu *m){
    if(m){m->selected_id=0;m->page=0;m->cursor=0;}
}
int nx_film_menu_action(nx_film_menu *m,enum nx_film_action a){
    if(!m)return -1;
    /* Keep wheel cursor aligned even if a preset was selected programmatically. */
    for(size_t i=0;i<nx_film_count();i++)
      if(PRESETS[i].id==canonical_id(m->selected_id)){m->cursor=(unsigned)i;break;}
    if(a==NX_ACT_PREV){m->cursor=(unsigned)((m->cursor+nx_film_count()-1)%nx_film_count());m->selected_id=PRESETS[m->cursor].id;return 0;}
    if(a==NX_ACT_NEXT){m->cursor=(unsigned)((m->cursor+1)%nx_film_count());m->selected_id=PRESETS[m->cursor].id;return 0;}
    if(a==NX_ACT_SELECT){m->selected_id=PRESETS[m->cursor].id;return 1;}
    if(a==NX_ACT_BACK){for(size_t i=0;i<nx_film_count();i++)if(PRESETS[i].id==m->selected_id){m->cursor=(unsigned)i;break;}return 0;}
    return -1;
}
/* Presets are absolute: no blending, strength, intensity or per-style gain slider. */
int nx_film_menu_store(const nx_film_menu *m,const char *path){
    if(!m||!path||!nx_film_by_id(m->selected_id))return -1;
    FILE *f=fopen(path,"w");if(!f)return -1;
    int ok=fprintf(f,"NX_FILM_MENU %u\npreset=%u\n",NX_FILM_MENU_VERSION,canonical_id(m->selected_id));
    int rc=fclose(f);return ok>0&&rc==0?0:-1;
}
int nx_film_menu_load(nx_film_menu *m,const char *path){
    if(!m||!path)return -1;
    FILE *f=fopen(path,"r");if(!f)return -1;
    unsigned version=0,id=0;
    int matched=fscanf(f,"NX_FILM_MENU %u\npreset=%u",&version,&id);
    fclose(f);
    if(matched!=2||(version!=1&&version!=NX_FILM_MENU_VERSION)||!nx_film_by_id(id))return -1;
    /* V1 strength is deliberately ignored: presets have fixed processing values. */
    id=canonical_id(id);
    m->selected_id=id;
    for(size_t i=0;i<nx_film_count();i++)if(PRESETS[i].id==id){m->cursor=(unsigned)i;break;}
    return 0;
}
int nx_film_lut_for_menu(const nx_film_menu *m,nx_rgb12 *lut){
    if(!m||!lut)return -1;
    const nx_film_preset *preset=nx_film_by_id(m->selected_id);if(!preset)return -1;
    nx_look_params p;nx_look_params_identity(&p);
    p.saturation=preset->saturation;
    p.shadow_gain=preset->shadow;
    p.highlight_gain=preset->highlight;
    p.gamma=preset->gamma;
    for(unsigned i=0;i<9;i++)p.film_color_matrix[i]=preset->channel_mix[i];
    return nx_look_build_lut18(lut,&p);
}
