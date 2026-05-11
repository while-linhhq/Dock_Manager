from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch
import yaml
from PIL import Image
from torchvision import transforms

from model import ReidEmbeddingNet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Evaluate Re-ID query/gallery retrieval.')
    parser.add_argument('--config', default='fine-tune/config.yaml')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding='utf-8'))
    reid_cfg = cfg['reid']
    device = torch.device(cfg.get('project', {}).get('device', 'cpu'))
    model = ReidEmbeddingNet(int(reid_cfg['embedding_dim'])).to(device)
    checkpoint = torch.load(reid_cfg['checkpoint'], map_location=device, weights_only=True)
    model.load_state_dict(checkpoint['model'])
    model.eval()
    transform = transforms.Compose(
        [
            transforms.Resize((int(reid_cfg['image_size']), int(reid_cfg['image_size']))),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    query = _load_split(Path(reid_cfg['data_dir']) / 'query', model, transform, device)
    gallery = _load_split(Path(reid_cfg['data_dir']) / 'gallery', model, transform, device)
    rank1 = _rank_at_k(query, gallery, 1)
    rank5 = _rank_at_k(query, gallery, 5)
    print(f'Rank-1: {rank1:.4f}')
    print(f'Rank-5: {rank5:.4f}')


def _load_split(root: Path, model, transform, device) -> list[tuple[str, np.ndarray]]:
    rows: list[tuple[str, np.ndarray]] = []
    for label_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        for image_path in sorted(label_dir.glob('*')):
            if image_path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
                continue
            image = transform(Image.open(image_path).convert('RGB')).unsqueeze(0).to(device)
            with torch.no_grad():
                embedding = model(image).cpu().numpy().reshape(-1)
            rows.append((label_dir.name, embedding))
    return rows


def _rank_at_k(
    query: list[tuple[str, np.ndarray]],
    gallery: list[tuple[str, np.ndarray]],
    k: int,
) -> float:
    if not query or not gallery:
        return 0.0
    hits = 0
    for label, embedding in query:
        scored = [
            (gallery_label, float(np.dot(embedding, gallery_embedding)))
            for gallery_label, gallery_embedding in gallery
        ]
        top = sorted(scored, key=lambda item: item[1], reverse=True)[:k]
        if any(gallery_label == label for gallery_label, _ in top):
            hits += 1
    return hits / len(query)


if __name__ == '__main__':
    main()
