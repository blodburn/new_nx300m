#ifndef NX300M_YCC420_MULTIMODEL_PROBE_H
#define NX300M_YCC420_MULTIMODEL_PROBE_H
#include <stddef.h>
#include <stdint.h>

/* HOST-ONLY and read-only. All three input planes must be independently
 * authorized SAME-STAGE COPIES, never camera DMA addresses. Model scores
 * never certify real NX300M 1.14 format, matrices, buffer ownership or ABI.
 */
enum nx_420_model {
 NX_420_BT601_FULL=0, NX_420_BT709_FULL=1,
 NX_420_BT601_LIMITED=2, NX_420_BT709_LIMITED=3,
 NX_420_MODEL_COUNT=4
};
enum nx_420_order { NX_420_ORDER_CBCR=0, NX_420_ORDER_CRCB=1 };
enum nx_420_model_verdict {
 NX_420_MODEL_INVALID=-1, NX_420_MODEL_INCONCLUSIVE=0,
 NX_420_MODEL_DISTINCT=1
};
typedef struct {
 uint32_t y_mae_milli, chroma_mae_milli, combined_mae_milli;
} nx_420_model_score;
typedef struct {
 uint64_t sampled_pairs, informative_pairs;
 nx_420_model_score candidates[NX_420_MODEL_COUNT][2];
 enum nx_420_model best_model;
 enum nx_420_order best_order;
 uint32_t best_gap_milli;
 enum nx_420_model_verdict verdict;
} nx_420_model_report;
enum nx_420_model_verdict nx_420_multimodel_probe(
 const uint8_t *y,size_t y_bytes,size_t y_stride,
 const uint8_t *chroma,size_t c_bytes,size_t c_stride,
 const uint8_t *rgb,size_t rgb_bytes,size_t rgb_stride,
 unsigned width,unsigned height,nx_420_model_report *report);
const char *nx_420_model_name(enum nx_420_model model);
#endif
