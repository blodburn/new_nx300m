CC ?= gcc
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer
LDLIBS = -lm
BASE = nx300m_host_ycc420_probe nx300m_host_native420_bridge nx300m_cycc_layout nx300m_host_jpeg_sink nx300m_shutter_jpeg_bridge nx300m_still_enhanced nx300m_image_enhance nx300m_camera_style_response nx300m_still_pipeline nx300m_capture_bridge nx300m_film_menu nx300m_preview_rgb nx300m_lut18 nx300m_look_builder nx300m_linear_prejpeg nx300m_bayer_prejpeg nx300m_film_keys
SOURCES = $(addprefix research/,$(addsuffix .c,$(BASE)))
TESTS = linear_prejpeg bayer_prejpeg bayer_row_emit host_jpeg_sink host_native420_bridge host_ycc420_probe shutter_jpeg_bridge camera_style_response film_menu image_enhance still_pipeline capture_bridge
BENCH_SOURCES = research/nx300m_host_native420_bridge.c research/nx300m_cycc_layout.c research/nx300m_host_jpeg_sink.c research/nx300m_bayer_prejpeg.c research/nx300m_camera_style_response.c research/nx300m_linear_prejpeg.c research/nx300m_film_menu.c research/nx300m_lut18.c research/nx300m_look_builder.c research/nx300m_preview_rgb.c
.PHONY: test bench probe clean
test:
	@mkdir -p .build outputs
	@set -e; for t in $(TESTS); do \
	  $(CC) $(CFLAGS) -Iresearch research/test_nx300m_$$t.c $(SOURCES) $(LDLIBS) -o .build/test_nx300m_$$t; \
	  ASAN_OPTIONS=detect_leaks=1 .build/test_nx300m_$$t; \
	done
	@python3 research/test_nx300m_jpeg_sof_probe.py
	@$(MAKE) --no-print-directory probe
	@python3 research/test_nx300m_host_ycc420_probe_cli.py
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
