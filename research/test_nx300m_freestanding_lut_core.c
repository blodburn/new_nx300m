/* Synthetic parity harness on GNU ARM32/QEMU. Loads freestanding module with
 * dlopen in a host-only process and compares against independent host oracle.
 * Does NOT link against Samsung camera libraries or touch firmware.
 */
#include "nx300m_freestanding_lut_core.h"
#include "nx300m_lut_grid_host.h"
#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef int (*core_fn)(const nx_rgb12 *,size_t,unsigned,
                       const nx_rgb12 *,nx_rgb12 *,size_t);
static uint32_t rng_state=0x129834fdu;
static uint32_t rnd(void){
 uint32_t x=rng_state;
 x^=x<<13;x^=x>>17;x^=x<<5;rng_state=x;
 return x;
}
static void test_grid(core_fn fn,unsigned grid){
 const size_t count=(size_t)grid*grid*grid;
 const size_t pixels=768u;
 nx_rgb12 *lut=malloc(count*sizeof(*lut));
 nx_rgb12 *src=malloc(pixels*sizeof(*src));
 nx_rgb12 *host=malloc(pixels*sizeof(*host));
 nx_rgb12 *plugin=malloc(pixels*sizeof(*plugin));
 nx_rgb12 *alias=malloc(pixels*sizeof(*alias));
 assert(lut&&src&&host&&plugin&&alias);
 for(size_t k=0;k<count;k++){
  lut[k].r=(uint16_t)(rnd()%5200u);
  lut[k].g=(uint16_t)(rnd()%4900u);
  lut[k].b=(uint16_t)(rnd()%4600u);
  lut[k].reserved=0u;
 }
 for(size_t k=0;k<pixels;k++){
  src[k].r=(uint16_t)(rnd()&0xffffu);
  src[k].g=(uint16_t)(rnd()&0xffffu);
  src[k].b=(uint16_t)(rnd()&0xffffu);
  src[k].reserved=0u;
 }
 const nx_rgb12 edge[]={
  {0,0,0,0},{1,2,3,0},{4095,4095,4095,0},
  {4094,4094,4094,0},{2048,2048,2048,0},
  {65535,65535,65535,0},{5000,0,1024,0}
 };
 for(unsigned k=0;k<sizeof(edge)/sizeof(edge[0]);k++)src[k]=edge[k];
 assert(nx_lut_grid_host_apply(lut,grid,src,host,pixels)==0);
 assert(fn(lut,count,grid,src,plugin,pixels)==0);
 assert(memcmp(host,plugin,pixels*sizeof(*host))==0);
 memcpy(alias,src,pixels*sizeof(*src));
 assert(fn(lut,count,grid,alias,alias,pixels)==0);
 assert(memcmp(host,alias,pixels*sizeof(*host))==0);
 nx_rgb12 guard={0xaaaa,0xbbbb,0xcccc,0xdddd},before=guard;
 assert(fn(lut,count-1u,grid,src,&guard,1u)==-1);
 assert(memcmp(&guard,&before,sizeof(guard))==0);
 assert(fn(lut,count,1u,src,&guard,1u)==-1);
 assert(fn(lut,count,66u,src,&guard,1u)==-1);
 assert(fn(lut,count,grid,NULL,&guard,1u)==-1);
 assert(fn(lut,count,grid,src,NULL,1u)==-1);
 assert(fn(NULL,count,grid,src,&guard,1u)==-1);
 assert(memcmp(&guard,&before,sizeof(guard))==0);
 free(alias);free(plugin);free(host);free(src);free(lut);
 printf("PASS freestanding LUT %u^3: 768 randomized RGB12 points + "
        "edge cases + in-place + invalid inputs, exact host parity\n",grid);
}
int main(int argc,char **argv){
 assert(argc==2 && argv[1]);
 void *handle=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);
 if(!handle){
  fprintf(stderr,"FAIL: dlopen standalone module: %s\n",dlerror());
  return 2;
 }
 void *pointer=dlsym(handle,"nx_film_core_apply_rgb12");
 if(!pointer){
  fprintf(stderr,"FAIL: expected module export missing\n");
  (void)dlclose(handle);
  return 2;
 }
 core_fn apply=(core_fn)pointer;
 test_grid(apply,2u);
 test_grid(apply,18u);
 test_grid(apply,65u);
 assert(dlclose(handle)==0);
 puts("PASS ARMv7/QEMU freestanding C ABI + no-libc 65-grid LUT, "
      "NOT camera loader or JPEG hook");
 return 0;
}
