#include "nx300m_film_menu.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static nx_rgb12 pixels[NX_LUT_COUNT];
int main(void){
    nx_film_menu m;nx_film_menu_init(&m);
    assert(nx_film_count()==13&&m.selected_id==0);
    for(size_t i=0;i<nx_film_count();i++){
        m.selected_id=nx_film_by_index(i)->id;
        assert(nx_film_lut_for_menu(&m,pixels)==0);
        assert(nx_film_by_index(i)->family<3);
    }
    for(unsigned id=300;id<=304;id++)assert(nx_film_by_id(id)->id==id-100);
    nx_film_menu_init(&m);
    assert(nx_film_menu_action(&m,NX_ACT_PREV)==0);
    assert(m.cursor==12&&m.selected_id==204); /* rotational wrap */
    assert(nx_film_menu_action(&m,NX_ACT_NEXT)==0);
    assert(m.cursor==0&&m.selected_id==0);
    assert(nx_film_menu_action(&m,NX_ACT_NEXT)==0&&m.selected_id==100);
    assert(nx_film_menu_action(&m,NX_ACT_SELECT)==1);
    assert(nx_film_menu_store(&m,"outputs/TEST_film_selection.cfg")==0);
    FILE *f=fopen("outputs/TEST_film_selection.cfg","r");assert(f);
    char line[128]={0};assert(fgets(line,sizeof(line),f));
    assert(strcmp(line,"NX_FILM_MENU 2\n")==0);
    assert(fgets(line,sizeof(line),f));assert(strcmp(line,"preset=100\n")==0);
    assert(fgetc(f)==EOF);assert(fclose(f)==0); /* No strength stored. */
    nx_film_menu n;nx_film_menu_init(&n);
    assert(nx_film_menu_load(&n,"outputs/TEST_film_selection.cfg")==0&&n.selected_id==100);
    /* V1 files used strength; loading preserves just selected fixed preset. */
    f=fopen("outputs/TEST_old_q3_selection.cfg","w");assert(f);
    assert(fputs("NX_FILM_MENU 1\npreset=304\nstrength=0.650000\n",f)>0);
    assert(fclose(f)==0);
    assert(nx_film_menu_load(&n,"outputs/TEST_old_q3_selection.cfg")==0);
    assert(n.selected_id==204&&n.cursor==12);
    assert(nx_film_lut_for_menu(&n,pixels)==0);
    assert(nx_film_menu_action(&n,NX_ACT_BACK)==0&&n.cursor==12);
    puts("PASS fixed Film Simulator presets, cyclic rotation, V2 strength-free persistence and legacy config migration");
    return 0;
}
