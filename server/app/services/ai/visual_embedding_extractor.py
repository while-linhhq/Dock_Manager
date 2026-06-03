from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class VisualEmbeddingExtractor:
    """ViT-oriented embedding extractor for vessel visual identification."""

    def __init__(
        self,
        *,
        model_path: str | None = None,
        backbone: str = 'vit_base_patch16_224',
        device: str = 'cpu',
        image_size: int = 224,
        embedding_dim: int = 1024,
    ) -> None:
        self._device = _normalize_torch_device(device)
        self._image_size = max(96, int(image_size))
        self._embedding_dim = max(64, int(embedding_dim))
        self._model_output_dim = self._embedding_dim
        self._model: Any | None = None
        self._preprocess: Any | None = None
        self._proj: Any | None = None
        self._backend = 'unavailable'
        self._load_model(model_path=model_path, backbone=backbone)

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    @property
    def model_output_dim(self) -> int:
        return int(self._model_output_dim)

    @property
    def vector_dim(self) -> int:
        """Dimension stored in Qdrant after optional projection."""
        return int(self._embedding_dim)

    def extract(self, crop_bgr: np.ndarray) -> np.ndarray | None:
        if crop_bgr is None or crop_bgr.size == 0:
            return None
        if self._model is None or self._preprocess is None:
            return None
        try:
            return self._extract_torch(crop_bgr)
        except Exception:
            logger.exception('Visual embedding extraction failed')
            return None

    def extract_batch(self, crops_bgr: list[np.ndarray]) -> list[np.ndarray | None]:
        if not crops_bgr:
            return []
        if self._model is None or self._preprocess is None:
            return [None for _ in crops_bgr]
        try:
            return self._extract_torch_batch(crops_bgr)
        except Exception:
            logger.exception('Visual embedding batch extraction failed')
            return [None for _ in crops_bgr]

    def _load_model(self, *, model_path: str | None, backbone: str) -> None:
        try:
            import torch
            from torchvision import transforms
        except Exception:
            logger.warning('Torch not available for VisualEmbeddingExtractor')
            return

        try:
            if model_path and Path(model_path).is_file():
                model = torch.jit.load(model_path, map_location=self._device)
                self._backend = 'torchscript-vit'
            else:
                try:
                    import timm
                except Exception:
                    logger.warning('timm not available, visual extractor disabled')
                    return
                model = timm.create_model(
                    backbone,
                    pretrained=True,
                    num_classes=0,
                    global_pool='avg',
                )
                self._backend = f'timm:{backbone}'

            model.eval()
            model.to(self._device)
            self._model = model
            raw_dim = int(getattr(model, 'num_features', 0) or 0)
            if raw_dim <= 0:
                import torch

                probe = torch.zeros(1, 3, self._image_size, self._image_size, device=self._device)
                with torch.no_grad():
                    out = model(probe)
                raw_dim = int(out.reshape(-1).shape[0])
            self._model_output_dim = max(1, raw_dim)
            if self._embedding_dim != self._model_output_dim:
                proj = torch.nn.Linear(
                    self._model_output_dim,
                    self._embedding_dim,
                    bias=False,
                )
                torch.nn.init.orthogonal_(proj.weight)
                proj.eval()
                proj.to(self._device)
                self._proj = proj
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
            logger.exception('Failed to load visual embedding model')
            self._model = None
            self._preprocess = None
            self._backend = 'unavailable'

    def _extract_torch(self, crop_bgr: np.ndarray) -> np.ndarray | None:
        import torch

        if self._model is None or self._preprocess is None:
            return None
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        tensor = self._preprocess(crop_rgb).unsqueeze(0).to(self._device)
        with torch.no_grad():
            embedding = self._model(tensor)
            if self._proj is not None:
                embedding = self._proj(embedding)
        vector = embedding.detach().cpu().numpy().reshape(-1).astype(np.float32)
        return _normalize_embedding(vector)

    def _extract_torch_batch(self, crops_bgr: list[np.ndarray]) -> list[np.ndarray | None]:
        import torch

        if self._model is None or self._preprocess is None:
            return [None for _ in crops_bgr]

        valid_indices: list[int] = []
        tensors = []
        for index, crop_bgr in enumerate(crops_bgr):
            if crop_bgr is None or crop_bgr.size == 0:
                continue
            crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            tensors.append(self._preprocess(crop_rgb))
            valid_indices.append(index)

        outputs: list[np.ndarray | None] = [None for _ in crops_bgr]
        if not tensors:
            return outputs

        batch = torch.stack(tensors, dim=0).to(self._device)
        with torch.no_grad():
            embeddings = self._model(batch)
            if self._proj is not None:
                embeddings = self._proj(embeddings)

        vectors = embeddings.detach().cpu().numpy()
        for output_index, source_index in enumerate(valid_indices):
            outputs[source_index] = _normalize_embedding(
                vectors[output_index].reshape(-1).astype(np.float32)
            )
        return outputs


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


def _normalize_embedding(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-8:
        return vector
    return vector / norm
