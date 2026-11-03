#!/bin/sh
# NX300M bounded read-only runtime metadata. Run ONLY in an existing,
# owner-authorized shell. No camera API, firmware write, proc memory access,
# root, user identifiers, network activity, process signals or file writes.
# Its output is a declaration/observation, NOT proof of capture activation.
set -u
if [ "$#" -ne 0 ]; then
  if [ "$#" -eq 1 ] && [ "$1" = "--help" ]; then
    printf '%s\n' 'NX300M read-only environment, memory, process-library metadata probe.'
    exit 0
  fi
  printf '%s\n' 'Only --help is supported.' >&2
  exit 2
fi
printf '%s\n' 'NX300M_FW114_RUNTIME_METADATA_V1'
printf '%s\n' 'probe_scope=read_only_metadata'
if command -v uname >/dev/null 2>&1; then
  machine=$(uname -m 2>/dev/null) || machine=unknown
else
  machine=unknown
fi
case "$machine" in
  armv7l|armv6l|armv5tel|aarch64|x86_64|i686|unknown)
    printf 'kernel_machine=%s\n' "$machine";;
  *) printf '%s\n' 'kernel_machine=other';;
esac
if [ -r /proc/meminfo ] && command -v awk >/dev/null 2>&1; then
  awk '
    $1=="MemTotal:"     { total=$2 }
    $1=="MemAvailable:" { avail=$2 }
    $1=="MemFree:"      { free=$2 }
    END {
      printf "mem_total_kib=%s\n", (total~/^[0-9]+$/?total:"unknown")
      printf "mem_available_kib=%s\n", (avail~/^[0-9]+$/?avail:"unknown")
      printf "mem_free_kib=%s\n", (free~/^[0-9]+$/?free:"unknown")
    }' /proc/meminfo
else
  printf '%s\n' 'mem_total_kib=unknown' 'mem_available_kib=unknown' 'mem_free_kib=unknown'
fi

camera_process=not_observed
camera_maps=not_observed
mm_photo=not_observed
sif=not_observed
capture_fw=not_observed
for task in /proc/[0-9]*; do
  [ -d "$task" ] || continue
  [ -r "$task/comm" ] || continue
  IFS= read -r comm < "$task/comm" || continue
  case "$comm" in
    *camera*|*Camera*|*capture*|*Capture*|*camd*)
      camera_process=observed
      if [ -r "$task/maps" ] && command -v grep >/dev/null 2>&1; then
        camera_maps=observed
        if grep -q 'libmm-photo[.]so' "$task/maps" 2>/dev/null; then
          mm_photo=observed
        fi
        if grep -q 'libsif[.]so' "$task/maps" 2>/dev/null; then
          sif=observed
        fi
        if grep -q 'libcapture-fw-slpcam-nx300[.]so' "$task/maps" 2>/dev/null; then
          capture_fw=observed
        fi
      fi
      ;;
  esac
done
printf 'camera_process=%s\n' "$camera_process"
printf 'camera_maps_readable=%s\n' "$camera_maps"
printf 'camera_libmm_photo_loaded=%s\n' "$mm_photo"
printf 'camera_libsif_loaded=%s\n' "$sif"
printf 'camera_libcapture_fw_loaded=%s\n' "$capture_fw"

# Explicitly FAIL CLOSED. These require independent, same-stage, authorized
# real capture evidence and physical recovery methods.
printf '%s\n' \
  'firmware_114_independently_authenticated=no' \
  'live_capture_callback_verified=no' \
  'live_ycc420_layout_verified=no' \
  'native_buffer_ownership_verified=no' \
  'calibration_recovery_verified=no' \
  'firmware_flash_permitted=no' \
  'firmware_write_performed=no'
