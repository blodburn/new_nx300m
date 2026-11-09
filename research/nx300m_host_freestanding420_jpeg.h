/* HOST ONLY: independent copied Y/C420 -> no-libc RGB stripe -> host JPEG.
 * NOT a Samsung firmware, native JPEG/EXIF ABI, or a camera loader hook.
 */
#ifndef NX300M_HOST_FREESTANDING420_JPEG_H
#define NX300M_HOST_FREESTANDING420_JPEG_H
#include "nx300m_host_owned420_snapshot.h"

/* Returns 0 only after a new JPEG is atomically published.
 * Returns 1 for Original bypass (no file access or re-encode).
 * Returns -1 on error; never replaces an existing destination.
 * The module_path is a HOST dlopen-able independent film-core DSO.
 * Caller Y/C, LUT, and transfer tables must be readable host allocations.
 * This adapter takes its own independent bounded snapshot before encoding;
 * it does NOT prove real camera/DMA pointer ownership or coherency.
 * Caller input job remains unchanged; rgb/rgb_bytes/rgb_stride are ignored
 * because this function allocates exactly one packed RGB888 scanline.
 * Original EXIF APP1 bytes are used only when caller explicitly supplies
 * them. Missing/invalid EXIF never causes synthesized camera metadata.
 */
/* Two-stage HOST simulation:
 * 1. nx_host_owned420_snapshot_take() copies independently owned Y/C/LUT.
 * 2. The caller may release/change the original buffers.
 * 3. This function encodes from the still-live, ready snapshot.
 * The caller must not mutate/release that snapshot during encoding.
 * Return 0 on new JPEG, -1 on error/no overwrite.
 * No camera capture, DMA synchronization, or native JPEG hook is supplied.
 */
int nx_host_freestanding420_jpeg_from_snapshot(
    const char *module_path,
    const nx_host_owned420_snapshot *snapshot,
    const char *new_jpeg_path,
    const uint8_t *original_exif_app1,
    size_t exif_bytes);

int nx_host_freestanding420_jpeg_copy(
    const char *module_path,
    const nx_film_owned420_hypothesis_job *copied_input,
    int original_bypass,
    const char *new_jpeg_path,
    const uint8_t *original_exif_app1,
    size_t exif_bytes);
#endif
