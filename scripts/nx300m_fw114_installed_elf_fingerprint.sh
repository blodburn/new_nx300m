#!/bin/sh
# NX300M installed camera-library identity probe — READ ONLY.
# Run MANUALLY in an existing owner-authorized camera shell.
# Only reads four fixed filenames in an explicitly supplied library dir.
# No root escalation, proc memory, DMA, device nodes, camera calls, firmware
# flashing, writes, process signals, network or personal identifiers.
# No file paths or machine IDs are printed.
set -u
if [ "$#" -eq 1 ] && [ "$1" = "--help" ]; then
    printf '%s\n' 'NX300M read-only installed camera ELF SHA-256 probe'
    printf '%s\n' 'Usage: sh nx300m_fw114_installed_elf_fingerprint.sh /absolute/library/dir'
    printf '%s\n' 'Requires a pre-authorized local shell. No device changes.'
    exit 0
fi
if [ "$#" -ne 1 ]; then
    printf '%s\n' 'Exactly one absolute library directory required.' >&2
    exit 2
fi
directory=$1
case "$directory" in
    /*) ;;
    *) printf '%s\n' 'Relative library directory rejected.' >&2; exit 2 ;;
esac
if [ ! -d "$directory" ] || [ -L "$directory" ]; then
    printf '%s\n' 'Library directory missing or symbolic link.' >&2
    exit 2
fi

# Use only BusyBox/Tizen-compatible facilities. No symlinks or oversized files.
fingerprint() {
    source_file=$1
    if [ ! -f "$source_file" ] || [ ! -r "$source_file" ] ||
       [ -L "$source_file" ]; then
        printf '%s\n' 'unknown unknown'
        return
    fi
    if ! command -v wc >/dev/null 2>&1 ||
       ! command -v tr >/dev/null 2>&1; then
        printf '%s\n' 'unknown unknown'
        return
    fi
    file_size=$(wc -c < "$source_file" 2>/dev/null) || file_size=
    file_size=$(printf '%s' "$file_size" | tr -d '[:space:]') || file_size=
    case "$file_size" in
        ''|*[!0-9]*) printf '%s\n' 'unknown unknown'; return ;;
    esac
    if [ "$file_size" -lt 52 ] || [ "$file_size" -gt 67108864 ]; then
        printf '%s\n' 'unknown unknown'
        return
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        result=$(sha256sum "$source_file" 2>/dev/null) || result=
    elif [ -x /bin/busybox ]; then
        result=$(/bin/busybox sha256sum "$source_file" 2>/dev/null) || result=
    else
        result=
    fi
    digest=${result%% *}
    case "$digest" in
        ''|*[!0123456789abcdef]*)
            printf '%s\n' 'unknown unknown'; return ;;
    esac
    if [ "${#digest}" -ne 64 ]; then
        printf '%s\n' 'unknown unknown'
        return
    fi
    printf '%s %s\n' "$digest" "$file_size"
}
printf '%s\n' 'NX300M_INSTALLED_CAMERA_ELF_SHA_V1'
printf '%s\n' 'probe_scope=read_only_installed_elf_files'
all_present=yes
for item in \
    photo:libmm-photo.so \
    sif:libsif.so \
    capture:libcapture-fw-slpcam-nx300.so \
    sysmmap:libsys-mmap-manager.so
do
    field=${item%%:*}
    filename=${item#*:}
    record=$(fingerprint "$directory/$filename")
    hash=${record%% *}
    length=${record#* }
    [ "$hash" != unknown ] || all_present=no
    printf '%s_sha256=%s\n' "$field" "$hash"
    printf '%s_bytes=%s\n' "$field" "$length"
done
printf 'all_four_files_read=%s\n' "$all_present"
printf '%s\n' \
    'manufacturer_firmware_authenticated=no' \
    'camera_binary_runtime_binding_verified=no' \
    'live_ycc420_layout_verified=no' \
    'dma_buffer_ownership_verified=no' \
    'firmware_flash_permitted=no' \
    'firmware_write_performed=no'
