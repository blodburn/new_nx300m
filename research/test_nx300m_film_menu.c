#include "nx300m_film_menu.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static nx_rgb12 pixels[NX_LUT_COUNT];
static void test_corrupt_config_never_changes_selection(void){
    const char *path="outputs/TEST_invalid_film_selection.cfg";
    static const char *bad[]={
        "",
        "NX_FILM_MENU 2\npreset=100", /* truncated last line */
        "NX_FILM_MENU 2\npreset=100\ntrailer=1\n",
        "NX_FILM_MENU 2\npreset=100\nstrength=0.5\n",
        "NX_FILM_MENU 2\npreset=999\n",
        "NX_FILM_MENU 2\npreset=42949672960\n",
        "NX_FILM_MENU 2\npreset=+100\n",
        "NX_FILM_MENU 2\npreset=100x\n",
        "NX_FILM_MENU 2\npreset= 100\n",
        "NX_FILM_MENU 1\npreset=304\nstrength=nan\n",
        "NX_FILM_MENU 1\npreset=304\nstrength=1e999\n",
        "NX_FILM_MENU 1\npreset=304\nstrength=0.5\njunk\n",
        "NX_FILM_MENU 3\npreset=100\n",
        "NX_FILM_MENU 2\npreset=100\n\n"
    };
    for(size_t i=0;i<sizeof(bad)/sizeof(bad[0]);i++){
        FILE *f=fopen(path,"wb");
        assert(f);
        const size_t n=strlen(bad[i]);
        assert(fwrite(bad[i],1,n,f)==n);
        assert(fclose(f)==0);
        nx_film_menu m;
        nx_film_menu_init(&m);
        m.selected_id=103;m.cursor=4;m.page=7;
        assert(nx_film_menu_load(&m,path)==-1);
        assert(m.selected_id==103&&m.cursor==4&&m.page==7);
    }
    assert(remove(path)==0);
    nx_film_menu m;nx_film_menu_init(&m);
    m.selected_id=104;m.cursor=5;
    assert(nx_film_menu_load(&m,path)==-1);
    assert(m.selected_id==104&&m.cursor==5);
}

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
    test_corrupt_config_never_changes_selection();
    puts("PASS fixed Film Simulator presets, strict V1/V2 config, corrupt-file rejection, unchanged active selection and legacy migration");
    return 0;
}
