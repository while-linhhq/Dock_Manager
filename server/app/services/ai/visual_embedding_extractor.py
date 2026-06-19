from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_DINOV2_FALLBACK_BACKBONES = (
    'vit_base_patch14_dinov2',
    'vit_base_patch14_dinov2.lvd142m',
)
_DINOV2_IMAGE_SIZE = 224


class VisualEmbeddingExtractor:
    """DINOv2-oriented embedding extractor for vessel visual identification."""

    def __init__(
        self,
        *,
        model_path: str | None = None,
        backbone: str = 'vit_base_patch14_dinov2',
        device: str = 'cpu',
        image_size: int = 224,
        embedding_dim: int = 768,
    ) -> None:
        self._device = _normalize_torch_device(device)
        self._image_size = max(96, int(image_size))
        self._requested_embedding_dim = max(64, int(embedding_dim))
        self._embedding_dim = self._requested_embedding_dim
        self._model_output_dim = self._embedding_dim
        self._model: Any | None = None
        self._preprocess: Any | None = None
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
        return int(self._embedding_dim)

    def extract(self, crop_bgr: np.ndarray) -> np.ndarray | None:
        if crop_bgr is None or crop_bgr.size == 0:
            return None
        if self._model is None:
            return None
        try:
            return self._extract_torch(crop_bgr)
        except Exception:
            logger.exception('Visual embedding extraction failed')
            return None

    def extract_batch(self, crops_bgr: list[np.ndarray]) -> list[np.ndarray | None]:
        if not crops_bgr:
            return []
        if self._model is None:
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
                model, resolved_backbone = _load_timm_backbone(
                    backbone,
                    image_size=self._image_size,
                )
                if model is None:
                    logger.warning('Could not load visual backbone=%s', backbone)
                    return
                self._backend = f'timm:{resolved_backbone}'

            model.eval()
            model.to(self._device)
            self._model = model
            raw_dim = int(getattr(model, 'num_features', 0) or 0)
            if raw_dim <= 0:
                probe = torch.zeros(1, 3, self._image_size, self._image_size, device=self._device)
                with torch.no_grad():
                    out = model(probe)
                raw_dim = int(out.reshape(-1).shape[0])
            self._model_output_dim = max(1, raw_dim)
            self._embedding_dim = self._model_output_dim
            if self._requested_embedding_dim != self._embedding_dim:
                logger.warning(
                    'VISUAL_EMBEDDING_DIM=%s ignored; using native backbone dim=%s',
                    self._requested_embedding_dim,
                    self._embedding_dim,
                )

            self._preprocess = transforms.Compose(
                [
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
        tensor = _letterbox_tensor(crop_bgr, self._image_size, self._preprocess).unsqueeze(0)
        tensor = tensor.to(self._device)
        with torch.no_grad():
            embedding = self._model(tensor)
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
            tensors.append(_letterbox_tensor(crop_bgr, self._image_size, self._preprocess))
            valid_indices.append(index)

        outputs: list[np.ndarray | None] = [None for _ in crops_bgr]
        if not tensors:
            return outputs

        batch = torch.stack(tensors, dim=0).to(self._device)
        with torch.no_grad():
            embeddings = self._model(batch)

        vectors = embeddings.detach().cpu().numpy()
        for output_index, source_index in enumerate(valid_indices):
            outputs[source_index] = _normalize_embedding(
                vectors[output_index].reshape(-1).astype(np.float32)
            )
        return outputs


def _load_timm_backbone(backbone: str, *, image_size: int) -> tuple[Any | None, str]:
    try:
        import timm
    except Exception:
        return _load_torch_hub_dinov2(image_size=image_size)

    candidates = [backbone, *(_DINOV2_FALLBACK_BACKBONES if 'dinov2' in backbone.lower() else ())]
    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            kwargs: dict[str, Any] = {
                'pretrained': True,
                'num_classes': 0,
            }
            if 'dinov2' in name.lower():
                kwargs['img_size'] = image_size
                kwargs['dynamic_img_size'] = True
            else:
                kwargs['global_pool'] = 'avg'

            model = timm.create_model(name, **kwargs)
            return model, name
        except Exception:
            logger.exception('timm backbone load failed for %s', name)
            continue

    if 'dinov2' in backbone.lower():
        return _load_torch_hub_dinov2(image_size=image_size)
    return None, backbone


def _load_torch_hub_dinov2(*, image_size: int) -> tuple[Any | None, str]:
    try:
        import torch
    except Exception:
        return None, 'dinov2_vitb14'

    hub_models = ('dinov2_vitb14', 'dinov2_vits14')
    for hub_name in hub_models:
        try:
            model = torch.hub.load('facebookresearch/dinov2', hub_name)
            model.eval()
            return model, f'torchhub:{hub_name}'
        except Exception:
            logger.exception('torch.hub DINOv2 load failed for %s', hub_name)
            continue
    return None, 'dinov2_vitb14'


def _letterbox_tensor(crop_bgr: np.ndarray, target_size: int, preprocess: Any) -> Any:
    import torch

    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    letterboxed = _letterbox_rgb(crop_rgb, target_size)
    return preprocess(letterboxed)


def _letterbox_rgb(image_rgb: np.ndarray, target_size: int) -> np.ndarray:
    height, width = image_rgb.shape[:2]
    if height <= 0 or width <= 0:
        return np.zeros((target_size, target_size, 3), dtype=np.uint8)
    scale = target_size / max(height, width)
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    resized = cv2.resize(image_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((target_size, target_size, 3), dtype=np.uint8)
    y0 = (target_size - new_h) // 2
    x0 = (target_size - new_w) // 2
    canvas[y0 : y0 + new_h, x0 : x0 + new_w] = resized
    return canvas


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
