/* HOST ONLY: independent copied Y/C420 -> no-libc RGB stripe -> host JPEG.
 * NOT a Samsung firmware, native JPEG/EXIF ABI, or a camera loader hook.
 */
#ifndef NX300M_HOST_FREESTANDING420_JPEG_H
#define NX300M_HOST_FREESTANDING420_JPEG_H
#include "nx300m_freestanding_owned420_bridge.h"

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
int nx_host_freestanding420_jpeg_copy(
    const char *module_path,
    const nx_film_owned420_hypothesis_job *copied_input,
    int original_bypass,
    const char *new_jpeg_path,
    const uint8_t *original_exif_app1,
    size_t exif_bytes);
#endif
