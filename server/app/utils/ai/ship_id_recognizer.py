import logging
import re

import cv2

from app.utils.ai.gpu_bootstrap import init_windows_cuda_path

logger = logging.getLogger(__name__)


def _gpu_actually_works() -> bool:
    """Smoke-test cuDNN bằng 1 conv tiny — phát hiện sớm mismatch cuDNN/CUDA
    (vd. paddle build cu120 + libcudnn.so.9) trước khi PaddleOCR rơi worker."""
    try:
        import paddle
        if paddle.device.cuda.device_count() <= 0:
            return False
        paddle.set_device("gpu:0")
        x = paddle.randn([1, 3, 8, 8])
        conv = paddle.nn.Conv2D(3, 4, 3)
        _ = conv(x)
        return True
    except Exception as exc:
        logger.warning("Paddle GPU probe failed (%s) — falling back to CPU OCR", exc)
        return False


class ShipIdRecognizer:
    def __init__(self, lang="en", use_gpu=None, show_log=False):
        """Khởi tạo PaddleOCR; auto fallback CPU nếu GPU/cuDNN không sẵn sàng."""
        init_windows_cuda_path("pre")
        import paddle

        if use_gpu is None:
            use_gpu = _gpu_actually_works()
        elif use_gpu:
            if not _gpu_actually_works():
                use_gpu = False

        paddle.set_device("gpu:0" if use_gpu else "cpu")
        init_windows_cuda_path("post")

        from paddleocr import PaddleOCR
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=use_gpu,
            show_log=show_log,
        )
        logger.info("ShipIdRecognizer initialized (device=%s)", "gpu" if use_gpu else "cpu")
        self.pattern = r"([A-Z50]{2})[-\s]?(\d{4})"

    @staticmethod
    def _ensure_min_side_bgr(img_bgr, min_side: int = 480):
        """Crop nhỏ khiến PP-OCR det/rec hay trả None hoặc bị lọc; upscale trước khi OCR."""
        if img_bgr is None or img_bgr.size == 0:
            return img_bgr
        h, w = img_bgr.shape[:2]
        m = min(h, w)
        if m >= min_side or m <= 0:
            return img_bgr
        scale = min_side / m
        return cv2.resize(
            img_bgr,
            (int(round(w * scale)), int(round(h * scale))),
            interpolation=cv2.INTER_CUBIC,
        )

    def preprocess(self, img_bgr):
        """
        Tiền xử lý ảnh: upscale nếu crop nhỏ (Paddle det hay trả None / drop ở kích thước gốc),
        rồi Grayscale + CLAHE. Không dùng Otsu nhị phân — dễ làm méo chữ số (vd. 6/5).
        """
        img_bgr = self._ensure_min_side_bgr(img_bgr)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def extract_ship_id(self, ocr_results):
        """
        Lọc mã tàu bằng RegEx từ kết quả OCR.
        """
        found_ids = []
        for line in ocr_results:
            # PaddleOCR 2.7 format: [[box], (text, conf)]
            if not line or len(line) < 2:
                continue
            text, prob = line[1]
            
            clean_text = text.upper().strip().replace(" ", "")
            match = re.search(self.pattern, clean_text)
            if match:
                prefix = match.group(1).replace("5", "S").replace("0", "O")
                number = match.group(2)
                final_id = f"{prefix}-{number}"
                found_ids.append({
                    "id": final_id, 
                    "confidence": float(prob), 
                    "raw_text": text
                })
        return found_ids

    def recognize_bgr(self, img_bgr):
        """
        Nhận dạng mã tàu từ ảnh BGR (crop).
        Chạy OCR trên cả ảnh gốc và ảnh đã tiền xử lý để tăng độ chính xác.
        """
        if img_bgr is None or img_bgr.size == 0:
            return []

        # 1. OCR trên ảnh gốc (cùng upscale tối thiểu như preprocess)
        res_orig = self.ocr.ocr(self._ensure_min_side_bgr(img_bgr), cls=True)
        
        # 2. OCR trên ảnh tiền xử lý
        processed = self.preprocess(img_bgr)
        processed_bgr = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
        res_proc = self.ocr.ocr(processed_bgr, cls=True)

        # Gộp kết quả
        all_lines = []
        if res_orig and res_orig[0]:
            all_lines.extend(res_orig[0])
        if res_proc and res_proc[0]:
            all_lines.extend(res_proc[0])

        ship_ids = self.extract_ship_id(all_lines)
        
        # Sắp xếp theo confidence và loại bỏ trùng lặp
        if not ship_ids:
            return []

        ship_ids.sort(key=lambda x: x["confidence"], reverse=True)
        unique_ids = {}
        for item in ship_ids:
            sid = item["id"]
            if sid not in unique_ids or item["confidence"] > unique_ids[sid]["confidence"]:
                unique_ids[sid] = item
        
        return list(unique_ids.values())
