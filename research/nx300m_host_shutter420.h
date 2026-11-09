#ifndef NX300M_HOST_SHUTTER420_H
#define NX300M_HOST_SHUTTER420_H

/* HOST-ONLY still-capture routing for an independent FILM SIMULATOR.
 * No Samsung camera API, firmware hook, DMA access or on-device JPEG/RAW.
 * Camera-facing control and buffer provenance are NOT established.
 */
#include "nx300m_tizen_film_controller.h"
#include "nx300m_shutter_jpeg_bridge.h"
#include "nx300m_host_freestanding420_jpeg.h"

typedef int (*nx_host_raw_copy_writer)(const void *data,size_t bytes,void *user);
typedef int (*nx_host_original_jpeg_writer)(void *user);

typedef struct {
    nx_save_mode mode;
    const nx_tizen_film_controller *film_controller;
    /* Must match COMMITTED selection, not the unconfirmed UI preview.
     * This is an association check, NOT proof of Fuji/Leica calibration.
     * Pixel LUT values are GENERATED from that confirmed preset by this
     * adapter and are NOT taken from copied_film_job->lut.
     */
    unsigned lut_preset_id;
    /* HOST copied Y/C and transfer tables. The lut, lut_nodes and grid
     * fields are ignored/replaced by the committed preset's LUT18. */
    const nx_film_owned420_hypothesis_job *copied_film_job;
    const char *freestanding_module_path;
    const char *new_film_jpeg_path;
    const uint8_t *original_exif_app1;
    size_t exif_bytes;

    /* RAW bytes are opaque and never processed by the film LUT. */
    const void *opaque_raw;
    size_t raw_bytes;
    nx_host_raw_copy_writer write_raw;
    /* Original must use the caller's trusted original JPEG path. It is
     * NEVER re-encoded by the independent film simulation module. */
    nx_host_original_jpeg_writer write_original_jpeg;
    void *user;
} nx_host_shutter420_request;

/* 0: all requested outputs complete; -1: invalid input or failed save.
 * Uses nx_shutter_result: flags are set only AFTER callback success.
 * For a non-Original film, validates and copies Y/C, LUT and transfer
 * tables into independent HOST allocations BEFORE calling write_raw().
 * Invalid film metadata therefore cannot leave a RAW-only side effect.
 * The RAW callback may reuse its original Y/C allocations without changing
 * JPEG pixels; the selected film ID and pre-RAW frame are pinned together.
 * RAW+JPEG still saves RAW first after this preflight. If later JPEG
 * encoding or output creation fails, returns -1 with raw_saved=1. There is
 * NO atomic two-file transaction and NO rollback of completed RAW writes.
 * No full-frame RGB staging or per-preset strength/Picture Wizard rewrite;
 * no multi-JPEG sidecars. JPEG uses the fixed LUT18 from the committed
 * selection, not caller-provided LUT bytes. Host JPEG is create-only.
 * Actual camera frame ownership, native capture callback and DMA
 * synchronization have NOT been verified.
 */
int nx_host_shutter420_save_committed(
    const nx_host_shutter420_request *request,
    nx_shutter_result *result);
#endif
