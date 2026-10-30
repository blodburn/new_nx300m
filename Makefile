CC ?= gcc
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer
LDLIBS = -lm
BASE = nx300m_host_capture_copy_adapter nx300m_picture_wizard_route_guard nx300m_tizen_keymap nx300m_tizen_film_controller nx300m_host_ycc420_probe nx300m_host_native420_bridge nx300m_cycc_layout nx300m_host_jpeg_sink nx300m_shutter_jpeg_bridge nx300m_still_enhanced nx300m_image_enhance nx300m_camera_style_response nx300m_still_pipeline nx300m_capture_bridge nx300m_film_menu nx300m_preview_rgb nx300m_lut18 nx300m_look_builder nx300m_linear_prejpeg nx300m_bayer_prejpeg nx300m_film_keys
SOURCES = $(addprefix research/,$(addsuffix .c,$(BASE)))
TESTS = linear_prejpeg bayer_prejpeg bayer_row_emit host_jpeg_sink host_native420_bridge host_ycc420_probe tizen_film_controller tizen_keymap picture_wizard_route_guard host_capture_copy_adapter shutter_jpeg_bridge camera_style_response film_menu image_enhance still_pipeline capture_bridge
BENCH_SOURCES = research/nx300m_host_native420_bridge.c research/nx300m_cycc_layout.c research/nx300m_host_jpeg_sink.c research/nx300m_bayer_prejpeg.c research/nx300m_camera_style_response.c research/nx300m_linear_prejpeg.c research/nx300m_film_menu.c research/nx300m_lut18.c research/nx300m_look_builder.c research/nx300m_preview_rgb.c
.PHONY: test bench probe efl-check efl-runtime-test tizen-efl clean
test:
	@mkdir -p .build outputs
	@set -e; for t in $(TESTS); do \
	  $(CC) $(CFLAGS) -Iresearch research/test_nx300m_$$t.c $(SOURCES) $(LDLIBS) -o .build/test_nx300m_$$t; \
	  ASAN_OPTIONS=detect_leaks=1 .build/test_nx300m_$$t; \
	done
	@python3 research/test_nx300m_jpeg_sof_probe.py
	@$(MAKE) --no-print-directory probe
	@python3 research/test_nx300m_host_ycc420_probe_cli.py
	@python3 research/test_nx300m_tizen_elf_audit.py
	@python3 research/test_nx300m_capture_elf_surface_audit.py
	@python3 research/test_nx300m_picture_wizard_abi_gate.py
	@sh -n scripts/nx300m_tizen_readonly_probe.sh
	@sh -n scripts/build_tizen_efl.sh
	@sh scripts/nx300m_tizen_readonly_probe.sh --help
	@$(MAKE) --no-print-directory efl-check
	@$(MAKE) --no-print-directory efl-runtime-test
efl-check:
	$(CC) -std=c11 -Wall -Wextra -Werror -Wpedantic -fsyntax-only -Iresearch/host_stub -Iresearch research/nx300m_tizen_filmsim_efl.c
efl-runtime-test:
	@mkdir -p .build
	$(CC) $(CFLAGS) -Iresearch/host_stub -Iresearch research/test_nx300m_tizen_efl_runtime.c research/nx300m_tizen_keymap.c research/nx300m_tizen_film_controller.c research/nx300m_film_menu.c research/nx300m_look_builder.c research/nx300m_lut18.c $(LDLIBS) -o .build/test_nx300m_tizen_efl_runtime
	@ASAN_OPTIONS=detect_leaks=1 .build/test_nx300m_tizen_efl_runtime >.build/efl_runtime_test.log 2>&1
	@grep '^PASS host EFL runtime simulation:' .build/efl_runtime_test.log
tizen-efl:
	@TIZEN_CC="$(TIZEN_CC)" TIZEN_SYSROOT="$(TIZEN_SYSROOT)" TIZEN_PKG_CONFIG_LIBDIR="$(TIZEN_PKG_CONFIG_LIBDIR)" sh scripts/build_tizen_efl.sh
probe:
	@mkdir -p .build
	$(CC) -std=c11 -Wall -Wextra -Werror -Wpedantic -O2 -Iresearch research/nx300m_host_ycc420_probe_cli.c research/nx300m_host_ycc420_probe.c -o .build/ycc420_probe
bench:
	@mkdir -p .build outputs
	$(CC) -std=c11 -Wall -Wextra -Werror -O3 -Iresearch research/bench_nx300m_bayer_prejpeg.c $(BENCH_SOURCES) -lm -o .build/bench_bayer
	.build/bench_bayer emit
	$(CC) -std=c11 -Wall -Wextra -Werror -O3 -Iresearch research/bench_nx300m_host_jpeg.c $(BENCH_SOURCES) -lm -o .build/bench_jpeg
	.build/bench_jpeg
	$(CC) -std=c11 -Wall -Wextra -Werror -O3 -Iresearch research/bench_nx300m_host_native420.c $(BENCH_SOURCES) -lm -o .build/bench_ycc
	.build/bench_ycc
clean:
	rm -rf .build
