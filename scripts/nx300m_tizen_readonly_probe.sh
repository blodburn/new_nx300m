#!/bin/sh
# NX300M Tizen read-only userspace environment probe.
# Run MANUALLY via an ALREADY authorized local shell; do not use it to obtain
# access or install/flash firmware. Does not use autoexec.sh, telnet or root.
# Never prints serial numbers, MAC addresses, saved networks or passwords.
# No filesystem writes, mounts, processes killed or network requests.
if [ "$#" -gt 0 ]; then
  case "$1" in
    --help|-h)
      printf '%s\n' 'NX300M Tizen environment probe (read-only). Run only in an existing authorized shell.'
      exit 0;;
    *)
      printf '%s\n' 'Unsupported argument (try --help)' >&2
      exit 2;;
  esac
fi
printf '%s\n' 'NX300M_TIZEN_READ_ONLY_ENV_PROBE=1'
printf '%s\n' 'NOTE=Informational only; does not prove firmware 1.14 compatibility'
if command -v uname >/dev/null 2>&1; then
  printf 'kernel_name='
  uname -s
  printf 'kernel_machine='
  uname -m
  printf 'kernel_release='
  uname -r
else
  printf '%s\n' 'kernel=UNKNOWN'
fi
if [ -r /etc/tizen-release ]; then
  printf 'tizen_release_present=yes\n'
else
  printf 'tizen_release_present=no\n'
fi
if [ -r /etc/os-release ]; then
  printf 'os_release_present=yes\n'
else
  printf 'os_release_present=no\n'
fi
for exe in /bin/sh /bin/busybox /usr/bin/busybox /usr/sbin/telnetd /usr/bin/ldd; do
  if [ -e "$exe" ]; then printf 'present=%s\n' "$exe"; fi
done
for pattern in /usr/lib/libeina.so* /usr/lib/libevas.so* /usr/lib/libecore.so* /usr/lib/libelementary.so* /lib/ld-linux.so* /lib/ld-uClibc.so*; do
  if [ -e "$pattern" ]; then printf 'library_path=%s\n' "$pattern"; fi
done
for sd in /mnt/mmc /mnt/sdcard; do
  if [ -d "$sd" ]; then printf 'removable_mount_present=%s\n' "$sd"; fi
done
printf '%s\n' 'FIRMWARE_VERSION=UNVERIFIED'
printf '%s\n' 'CAMERA_NATIVE_YCC_BUFFER=UNVERIFIED'
printf '%s\n' 'NO_FIRMWARE_MODIFICATION_PERFORMED=yes'
