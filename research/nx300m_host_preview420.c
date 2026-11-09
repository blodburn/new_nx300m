#include "nx300m_host_preview420.h"
#include "nx300m_film_menu.h"
#include "nx300m_host_owned420_snapshot.h"
#include <dlfcn.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* This stages HOST pixels, not a target camera display or DMA allocation. */
#define NX_HOST_PREVIEW_MAX_FRAME_BYTES ((size_t)64u*1024u*1024u)
typedef int (*nx_render_rows_fn)(const nx_film_owned420_hypothesis_job *,
                                 unsigned,unsigned);

static int overlap(const void *a,size_t an,const void *b,size_t bn){
    const uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(!a||!b||an==0u||bn==0u||
       an>UINTPTR_MAX-x||bn>UINTPTR_MAX-y)return 1;
    return x<y+bn&&y<x+an;
}
int nx_host_preview420_apply(const nx_host_preview420_request *request,
                             unsigned *rendered_id){
    if(!request||!request->controller)return NX_HOST_PREVIEW420_INVALID;
    nx_tizen_film_view view;
    if(nx_tizen_film_view_state(request->controller,&view)!=0)
        return NX_HOST_PREVIEW420_INVALID;
    const unsigned active_id=view.open?view.preview_id:view.committed_id;
    const nx_film_preset *preset=nx_film_by_id(active_id);
    if(!preset||preset->id!=active_id)return NX_HOST_PREVIEW420_INVALID;

    /* Samsung Original remains entirely outside this renderer. */
    if(active_id==0u){
        if(rendered_id)*rendered_id=0u;
        return NX_HOST_PREVIEW420_BYPASSED;
    }
    const nx_film_owned420_hypothesis_job *in=request->copied_input;
    if(!in||!request->output_rgb||!request->freestanding_module_path||
       !request->freestanding_module_path[0]||!in->width||!in->height)
        return NX_HOST_PREVIEW420_INVALID;

    const size_t packed=(size_t)in->width*3u;
    if(in->width>8192u||in->height>8192u||
       in->height>SIZE_MAX/packed||
       request->output_stride<packed||request->output_stride>65536u)
        return NX_HOST_PREVIEW420_INVALID;
    const size_t stage_bytes=packed*in->height;
    if(stage_bytes>NX_HOST_PREVIEW_MAX_FRAME_BYTES||
       (in->height-1u)>(SIZE_MAX-packed)/request->output_stride)
        return NX_HOST_PREVIEW420_INVALID;
    const size_t output_span=(size_t)(in->height-1u)*
                             request->output_stride+packed;
    if(request->output_bytes<output_span||
       output_span>UINTPTR_MAX-(uintptr_t)request->output_rgb)
        return NX_HOST_PREVIEW420_INVALID;

    /* Prevent publishing over any input or metadata range. Pointers are
     * caller-supplied host allocations, not authenticated DMA extents. */
    const uint8_t *out=request->output_rgb;
    if(overlap(out,output_span,in,sizeof(*in))||
       overlap(out,output_span,request,sizeof(*request))||
       overlap(out,output_span,request->controller,
               sizeof(*request->controller))||
       overlap(out,output_span,in->y,in->y_bytes)||
       overlap(out,output_span,in->chroma,in->chroma_bytes)||
       overlap(out,output_span,in->decode_srgb,256u*sizeof(uint16_t))||
       overlap(out,output_span,in->encode_srgb,4096u))
        return NX_HOST_PREVIEW420_INVALID;
    if(rendered_id&&overlap(out,output_span,rendered_id,sizeof(*rendered_id)))
        return NX_HOST_PREVIEW420_INVALID;

    nx_rgb12 *lut=malloc((size_t)NX_LUT_COUNT*sizeof(*lut));
    if(!lut)return NX_HOST_PREVIEW420_INVALID;
    nx_film_menu selected;
    nx_film_menu_init(&selected);
    selected.selected_id=active_id;
    int result=NX_HOST_PREVIEW420_INVALID;
    if(nx_film_lut_for_menu(&selected,lut)!=0)goto cleanup_lut;
    nx_film_owned420_hypothesis_job copied=*in;
    copied.lut=lut;
    copied.lut_nodes=NX_LUT_COUNT;
    copied.grid=NX_LUT_GRID;
    nx_host_owned420_snapshot snapshot={0};
    if(nx_host_owned420_snapshot_take(&snapshot,&copied)!=0)
        goto cleanup_lut;
    uint8_t *stage=malloc(stage_bytes);
    if(!stage)goto cleanup_snapshot;
    void *module=dlopen(request->freestanding_module_path,
                        RTLD_NOW|RTLD_LOCAL);
    if(!module)goto cleanup_stage;
    nx_render_rows_fn render=(nx_render_rows_fn)
        dlsym(module,"nx_film_core_render_owned420_rows_hypothesis");
    if(!render)goto cleanup_module;
    nx_film_owned420_hypothesis_job job=snapshot.job;
    job.rgb=stage;
    job.rgb_stride=packed;
    job.rgb_bytes=stage_bytes;
    if(render(&job,0u,job.height)!=0)goto cleanup_module;

    /* Only a complete frame can be published; padding stays untouched. */
    for(unsigned y=0u;y<job.height;y++)
        memcpy(request->output_rgb+(size_t)y*request->output_stride,
               stage+(size_t)y*packed,packed);
    if(rendered_id)*rendered_id=active_id;
    result=NX_HOST_PREVIEW420_APPLIED;
cleanup_module:
    (void)dlclose(module);
cleanup_stage:
    free(stage);
cleanup_snapshot:
    nx_host_owned420_snapshot_release(&snapshot);
cleanup_lut:
    free(lut);
    return result;
}
