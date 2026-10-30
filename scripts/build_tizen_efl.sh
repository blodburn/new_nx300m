#!/bin/sh
# OFFLINE ARM/Tizen EFL build helper, never flashes or executes on camera.
set -eu
if [ -z "${TIZEN_CC:-}" ] || [ -z "${TIZEN_SYSROOT:-}" ] || [ -z "${TIZEN_PKG_CONFIG_LIBDIR:-}" ]; then
  echo 'REFUSED: verified TIZEN_CC, TIZEN_SYSROOT and TIZEN_PKG_CONFIG_LIBDIR required' >&2
  exit 2
fi
if [ ! -d "$TIZEN_SYSROOT" ] || [ ! -d "$TIZEN_PKG_CONFIG_LIBDIR" ]; then
  echo 'REFUSED: verified target sysroot or EFL pkgconfig directory missing' >&2
  exit 2
fi
command -v "$TIZEN_CC" >/dev/null 2>&1 || { echo 'REFUSED: compiler absent' >&2; exit 2; }
command -v pkg-config >/dev/null 2>&1 || exit 2
command -v readelf >/dev/null 2>&1 || exit 2
if ! PKG_CONFIG_SYSROOT_DIR="$TIZEN_SYSROOT" PKG_CONFIG_LIBDIR="$TIZEN_PKG_CONFIG_LIBDIR" pkg-config --exists elementary; then
  echo 'REFUSED: target Elementary EFL pkg-config metadata missing' >&2
  exit 2
fi
EFL_FLAGS=$(PKG_CONFIG_SYSROOT_DIR="$TIZEN_SYSROOT" PKG_CONFIG_LIBDIR="$TIZEN_PKG_CONFIG_LIBDIR" pkg-config --cflags --libs elementary)
case "$EFL_FLAGS" in *host_stub*) echo 'REFUSED: host declaration stub cannot be linked' >&2; exit 2;; esac
mkdir -p .build
# Flags come from the separately verified target EFL pkg-config directory.
# shellcheck disable=SC2086
"$TIZEN_CC" --sysroot="$TIZEN_SYSROOT" -std=c11 -Wall -Wextra -Werror -Iresearch \
  research/nx300m_tizen_filmsim_efl.c \
  research/nx300m_tizen_keymap.c research/nx300m_tizen_film_controller.c \
  research/nx300m_film_menu.c research/nx300m_look_builder.c \
  research/nx300m_lut18.c $EFL_FLAGS -lm -o .build/nx300m_filmsim_efl
if ! readelf -h .build/nx300m_filmsim_efl | grep -q 'Class:.*ELF32' ||
   ! readelf -h .build/nx300m_filmsim_efl | grep -q 'Machine:.*ARM' ||
   ! readelf -h .build/nx300m_filmsim_efl | grep -q 'Version5'; then
  rm -f .build/nx300m_filmsim_efl
  echo 'REFUSED: resulting ELF not ARM32 EABI5; deleted bad output' >&2
  exit 3
fi
echo 'HOST-CROSS-BUILT ARM EABI5. NOT verified on actual NX300M firmware 1.14.'
