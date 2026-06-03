from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.services.ai.visual_embedding_extractor import VisualEmbeddingExtractor

logger = logging.getLogger(__name__)


class EmbeddingExtractor:
    """
    Extract a stable visual descriptor for cross-camera Re-ID.

    Production path: torch/torchvision ResNet18 or a fine-tuned TorchScript model.
    Fallback path: HSV + grayscale histograms, so Re-ID still works without extra
    dependencies or custom weights.
    """

    def __init__(
        self,
        model_path: str | None = None,
        device: str = 'cpu',
        image_size: int = 224,
        *,
        use_visual_model: bool = False,
        visual_model_path: str | None = None,
        visual_backbone: str = 'vit_base_patch16_224',
        visual_embedding_dim: int = 1024,
        visual_image_size: int = 224,
        visual_device: str | None = None,
    ) -> None:
        self._device = _normalize_torch_device(device)
        self._image_size = max(64, int(image_size))
        self._model: Any | None = None
        self._preprocess: Any | None = None
        self._backend = 'histogram'
        self._visual_extractor: VisualEmbeddingExtractor | None = None
        if use_visual_model:
            self._visual_extractor = VisualEmbeddingExtractor(
                model_path=visual_model_path,
                backbone=visual_backbone,
                device=visual_device or device,
                image_size=visual_image_size,
                embedding_dim=visual_embedding_dim,
            )
            if self._visual_extractor.backend != 'unavailable':
                self._backend = self._visual_extractor.backend
        self._load_torch_model(model_path)

    @property
    def backend(self) -> str:
        return self._backend

    def extract(self, crop_bgr: np.ndarray) -> np.ndarray | None:
        if crop_bgr is None or crop_bgr.size == 0:
            return None
        if self._visual_extractor is not None:
            visual_vector = self._visual_extractor.extract(crop_bgr)
            if visual_vector is not None:
                return visual_vector
        if self._model is not None:
            try:
                return self._extract_torch(crop_bgr)
            except Exception:
                logger.exception('Torch embedding extraction failed, falling back to histogram')
        return self._extract_histogram(crop_bgr)

    def _load_torch_model(self, model_path: str | None) -> None:
        try:
            import torch
            from torchvision import models, transforms
        except Exception:
            return

        try:
            if model_path and Path(model_path).is_file():
                model = torch.jit.load(model_path, map_location=self._device)
                self._backend = 'torchscript'
            else:
                weights = models.ResNet18_Weights.DEFAULT
                base = models.resnet18(weights=weights)
                model = torch.nn.Sequential(*(list(base.children())[:-1]))
                self._backend = 'resnet18'

            model.eval()
            model.to(self._device)
            self._model = model
            self._preprocess = transforms.Compose(
                [
                    transforms.ToPILImage(),
                    transforms.Resize((self._image_size, self._image_size)),
                    transforms.ToTensor(),
                    transforms.Normalize(
                        mean=[0.485, 0.456, 0.406],
                        std=[0.229, 0.224, 0.225],
                    ),
                ]
            )
        except Exception:
            logger.exception('Failed to load embedding model')
            self._model = None
            self._preprocess = None
            self._backend = 'histogram'

    def _extract_torch(self, crop_bgr: np.ndarray) -> np.ndarray | None:
        import torch

        if self._model is None or self._preprocess is None:
            return None
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        tensor = self._preprocess(crop_rgb).unsqueeze(0).to(self._device)
        with torch.no_grad():
            embedding = self._model(tensor)
        vector = embedding.detach().cpu().numpy().reshape(-1).astype(np.float32)
        return normalize_embedding(vector)

    def _extract_histogram(self, crop_bgr: np.ndarray) -> np.ndarray:
        resized = cv2.resize(crop_bgr, (128, 128), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        hist_h = cv2.calcHist([hsv], [0], None, [32], [0, 180]).flatten()
        hist_s = cv2.calcHist([hsv], [1], None, [32], [0, 256]).flatten()
        hist_v = cv2.calcHist([hsv], [2], None, [32], [0, 256]).flatten()
        hist_gray = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten()
        embedding = np.concatenate([hist_h, hist_s, hist_v, hist_gray]).astype(np.float32)
        return normalize_embedding(embedding)


def normalize_embedding(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-8:
        return vector
    return vector / norm


def cosine_similarity(left: np.ndarray | None, right: np.ndarray | None) -> float:
    if left is None or right is None:
        return 0.0
    left_vector = normalize_embedding(left)
    right_vector = normalize_embedding(right)
    if left_vector.shape != right_vector.shape:
        return 0.0
    return float(np.clip(np.dot(left_vector, right_vector), -1.0, 1.0))


def _normalize_torch_device(device: str | int | None) -> str:
    raw = str(device or 'cpu').strip().lower()
    if raw in {'', 'none'}:
        return 'cpu'
    if raw.isdigit():
        try:
            import torch

            if torch.cuda.is_available():
                return f'cuda:{raw}'
        except Exception:
            pass
        return 'cpu'
    if raw == 'cuda':
        return 'cuda:0'
    return raw
