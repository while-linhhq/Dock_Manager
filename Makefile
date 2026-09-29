# ============================================================================
#  Dock Manager — điều khiển môi trường LOCAL
#
#  `make`  →  bật docker deps  →  chạy backend+client  →  kiểm tra sức khoẻ.
#
#  server/.env đã được chuyển sang hạ tầng LOCAL (127.0.0.1): Postgres, Redis,
#  Qdrant, MinIO. Riêng block ZALO_* giữ nguyên giá trị thật (webhook/token) và
#  RTSP trỏ camera thật — hai thứ này không thể local hoá.
#  Bản prod cũ nằm ở server/.env.bak.*-prod-infra nếu cần khôi phục.
#  Chỉ dùng `python scripts/env_get.py --json` để xem config (đã che secret).
# ============================================================================

SHELL        := /bin/bash
ROOT         := $(patsubst %/,%,$(dir $(realpath $(firstword $(MAKEFILE_LIST)))))
CONDA_SH     := $(HOME)/miniconda3/etc/profile.d/conda.sh
CONDA_ENV    ?= bason-dock
RUN_DIR      := .run
BACKEND_PORT ?= 8000
CLIENT_PORT  ?= 5173

# PIPELINE=1 bật pipeline AI tự khởi động (đọc RTSP + ghi media vào MinIO local).
# PIPELINE=0 chỉ lên API/UI. Dùng được cho mọi target: make start PIPELINE=0
PIPELINE ?= 1

# Kích hoạt conda env. Không cần nạp .env: app tự đọc server/.env qua
# pydantic-settings, và docker compose tự đọc .env cùng thư mục.
CONDA := . "$(CONDA_SH)" && conda activate $(CONDA_ENV)
PYX   := $(CONDA)

.DEFAULT_GOAL := all
.PHONY: all help up down start stop restart backend client dev-api \
        check config-diff engines verify-engines bench ab-detect test db shell seed ps logs logs-f clean

# ------------------------------------------------------------------ mặc định
all: up start check

help:
	@printf '\n\033[1mDock Manager — lệnh local\033[0m\n\n'
	@printf '  \033[36mmake\033[0m                 bật deps + chạy backend&client + kiểm tra sức khoẻ\n'
	@printf '  \033[36mmake start\033[0m            chạy backend + client ở nền (log trong %s/)\n' "$(RUN_DIR)"
	@printf '  \033[36mmake stop\033[0m             dừng backend + client + dọn OCR worker mồ côi\n'
	@printf '  \033[36mmake restart\033[0m          stop rồi start lại\n'
	@printf '  \033[36mmake backend\033[0m          chạy API ở foreground (:$(BACKEND_PORT))\n'
	@printf '  \033[36mmake client\033[0m           chạy Vite ở foreground (:$(CLIENT_PORT))\n'
	@printf '  \033[36mmake check\033[0m            kiểm tra sức khoẻ toàn bộ (~10s, không chạy test)\n'
	@printf '  \033[36mmake test\033[0m             pytest server/app/tests\n'
	@printf '  \033[36mmake config-diff\033[0m      key nào trong DB (port_configs) ghi đè .env\n'
	@printf '  \033[36mmake engines\033[0m          build TensorRT .engine cho model AI (chạy 1 lần/máy, cần GPU)\n'
	@printf '  \033[36mmake verify-engines\033[0m   đối chiếu .pt vs .engine + đo tốc độ\n'
	@printf '  \033[36mmake bench\033[0m           đo VRAM · RAM · CPU · độ trễ: bản gốc vs engine\n'
	@printf '  \033[36mmake ab-detect\033[0m       A/B đường tiền xử lý detection (CLAHE) trên frame thật\n\n'
	@printf '  \033[36mmake up\033[0m / \033[36mdown\033[0m        bật / tắt container db·minio·redis·qdrant (giữ data)\n'
	@printf '  \033[36mmake ps\033[0m               trạng thái container + tiến trình + cổng\n'
	@printf '  \033[36mmake logs\033[0m / \033[36mlogs-f\033[0m     xem log backend&client (logs-f để theo dõi)\n'
	@printf '  \033[36mmake db\033[0m               mở psql vào DB local\n'
	@printf '  \033[36mmake seed\033[0m             tạo schema + seed (app.db.init_db)\n'
	@printf '  \033[36mmake clean\033[0m            xoá log/PID tạm (KHÔNG xoá dữ liệu)\n\n'
	@printf '  Tuỳ chọn: \033[36mPIPELINE=0\033[0m tắt pipeline AI  ·  \033[36mCONDA_ENV=name\033[0m đổi env\n'
	@printf '  Đăng nhập local: \033[1madmin / admin123\033[0m\n\n'

# -------------------------------------------------------------------- docker
up:
	@printf '▶ Docker deps (db · minio · redis · qdrant)\n'
	@cd server && docker compose up -d db minio minio-init redis qdrant >/dev/null 2>&1 \
	  || { printf '  ✗ docker compose thất bại\n'; exit 1; }
	@for c in server-db-1 server-minio-1 server-redis-1 server-qdrant-1; do \
	  h=""; \
	  for i in $$(seq 1 30); do \
	    h=$$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}ok{{end}}' $$c 2>/dev/null); \
	    if [ "$$h" = "healthy" ] || [ "$$h" = "ok" ]; then break; fi; \
	    sleep 1; \
	  done; \
	  if [ "$$h" = "healthy" ] || [ "$$h" = "ok" ]; then \
	    printf '  ✓ %-18s %s\n' "$$c" "$$h"; \
	  else \
	    printf '  ✗ %-18s %s\n' "$$c" "$${h:-missing}"; \
	  fi; \
	done

down:
	@printf '▶ Tắt container (dữ liệu vẫn giữ trong server/app/data-docker)\n'
	@cd server && docker compose stop
	@printf '✓ Đã tắt container\n'

# ------------------------------------------------------------- chạy nền
# Idempotent: cái nào đang chạy thì bỏ qua (dùng `make restart` để khởi động lại).
start:
	@PIPELINE=$(PIPELINE) BACKEND_PORT=$(BACKEND_PORT) CLIENT_PORT=$(CLIENT_PORT) \
	  CONDA_ENV=$(CONDA_ENV) bash scripts/local_start.sh

stop:
	@CONDA_ENV=$(CONDA_ENV) bash scripts/local_stop.sh

restart: stop start

# --------------------------------------------------------------- foreground
backend:
	@$(PYX); export AUTOSTART_PIPELINE=$(PIPELINE); cd server && python run_dev.py

client:
	@cd client && pnpm run dev

# Biến thể tiện dụng: API/UI không bật pipeline AI
dev-api: PIPELINE=0
dev-api: start check

# ------------------------------------------------------------------ kiểm tra
check:
	@bash scripts/local_check.sh

# Xem key nào trong DB (port_configs) đang ghi đè .env — DB là lớp ưu tiên cao hơn.
config-diff:
	@python3 scripts/config_diff.py

# Build TensorRT engine cho model AI. Engine gắn cứng GPU + phiên bản TensorRT nên
# phải build lại trên từng máy; máy chưa có engine vẫn chạy .pt bình thường.
#   make engines                      # YOLO + DINOv2, fp16
#   make engines ENGINE_ARGS="--target yolo --force"
engines:
	@$(PYX); python scripts/export_engines.py $(ENGINE_ARGS)

# Đối chiếu .pt vs .engine (box YOLO, cosine DINOv2) và đo ms/frame.
verify-engines:
	@$(PYX); python scripts/verify_engines.py $(VERIFY_ARGS)

# Đo tài nguyên: VRAM · RAM · CPU · độ trễ của bản gốc vs engine (nên make stop trước cho sạch số).
#   make bench                      # cả YOLO + DINOv2
#   make bench BENCH_ARGS="--target yolo --iterations 50"
bench:
	@$(PYX); python scripts/bench_models.py $(BENCH_ARGS)

#   make ab-detect                  # A/B đường tiền xử lý detection (CLAHE) trên frame thật
#   make ab-detect AB_ARGS="--candidate detect-scale --detect-scale 0.5 --iou-gate 0.95"
ab-detect:
	@$(PYX); python scripts/ab_detect.py $(AB_ARGS)

test:
	@$(PYX); cd server && python -m pytest app/tests -q --no-header -p no:cacheprovider

# ------------------------------------------------------------------ tiện ích
db:
	@docker exec -it -e PGPASSWORD="$$(python3 scripts/env_get.py POSTGRES_PASSWORD postgres)" \
	  server-db-1 psql -U "$$(python3 scripts/env_get.py POSTGRES_USER postgres)" \
	  -d "$$(python3 scripts/env_get.py POSTGRES_DB demo_db)"

shell:
	@$(PYX); cd server && exec $$SHELL

seed:
	@$(PYX); cd server && python -m app.db.init_db

ps:
	@printf '\033[1mContainer\033[0m\n'
	@docker ps --filter name=server- --format '  {{.Names}}\t{{.Status}}\t{{.Ports}}' | sed 's/\t/  /g'
	@printf '\033[1mTiến trình\033[0m\n'
	@for f in $(RUN_DIR)/backend.pid $(RUN_DIR)/client.pid; do \
	  n=$$(basename $$f .pid); \
	  if [ -f $$f ] && kill -0 "$$(cat $$f)" 2>/dev/null; then \
	    printf '  ✓ %-8s pid %s\n' "$$n" "$$(cat $$f)"; \
	  else \
	    printf '  · %-8s không chạy\n' "$$n"; \
	  fi; \
	done
	@printf '\033[1mCổng\033[0m\n'
	@for p in $(BACKEND_PORT) $(CLIENT_PORT) 5432 9100 9101 6379 6333; do \
	  if timeout 1 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/$$p" 2>/dev/null; then \
	    printf '  ✓ %s\n' "$$p"; else printf '  · %s (đóng)\n' "$$p"; fi; \
	done

logs:
	@printf '\033[1m── backend (%s/backend.log) ──\033[0m\n' "$(RUN_DIR)"
	@tail -n 30 $(RUN_DIR)/backend.log 2>/dev/null || echo '  (chưa có log)'
	@printf '\n\033[1m── client (%s/client.log) ──\033[0m\n' "$(RUN_DIR)"
	@tail -n 15 $(RUN_DIR)/client.log 2>/dev/null || echo '  (chưa có log)'

logs-f:
	@tail -n 20 -f $(RUN_DIR)/backend.log $(RUN_DIR)/client.log

# Không xoá PID file của tiến trình đang chạy — nếu không sẽ mất đường dừng chúng.
clean:
	@for f in $(RUN_DIR)/backend.pid $(RUN_DIR)/client.pid; do \
	  if [ -f $$f ] && kill -0 "$$(cat $$f)" 2>/dev/null; then \
	    printf '✗ %s vẫn đang chạy (pid %s) — chạy `make stop` trước.\n' "$$(basename $$f .pid)" "$$(cat $$f)"; \
	    exit 1; \
	  fi; \
	done
	@printf '▶ Xoá log/PID tạm trong %s/\n' "$(RUN_DIR)"
	@rm -rf $(RUN_DIR)
	@find server -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@printf '✓ Xong (dữ liệu DB/MinIO không bị ảnh hưởng)\n'
