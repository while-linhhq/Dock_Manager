from __future__ import annotations

import argparse
from pathlib import Path

import torch
import yaml
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

from model import ReidEmbeddingNet


class VesselCropDataset(Dataset):
    def __init__(self, root: Path, image_size: int) -> None:
        self.samples: list[tuple[Path, int]] = []
        self.label_to_id: dict[str, int] = {}
        for label_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            label_id = self.label_to_id.setdefault(label_dir.name, len(self.label_to_id))
            for image_path in sorted(label_dir.glob('*')):
                if image_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}:
                    self.samples.append((image_path, label_id))
        self.transform = transforms.Compose(
            [
                transforms.Resize((image_size, image_size)),
                transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.15),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        image_path, label_id = self.samples[index]
        image = Image.open(image_path).convert('RGB')
        return self.transform(image), torch.tensor(label_id, dtype=torch.long)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Train ship Re-ID embedding model.')
    parser.add_argument('--config', default='fine-tune/config.yaml')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding='utf-8'))
    reid_cfg = cfg['reid']
    device = torch.device(cfg.get('project', {}).get('device', 'cpu'))
    dataset = VesselCropDataset(Path(reid_cfg['data_dir']) / 'train', int(reid_cfg['image_size']))
    if len(dataset) == 0:
        raise RuntimeError('No Re-ID training samples found')

    loader = DataLoader(
        dataset,
        batch_size=int(reid_cfg['batch']),
        shuffle=True,
        num_workers=2,
        drop_last=True,
    )
    model = ReidEmbeddingNet(int(reid_cfg['embedding_dim'])).to(device)
    classifier = torch.nn.Linear(int(reid_cfg['embedding_dim']), len(dataset.label_to_id)).to(device)
    optimizer = torch.optim.AdamW(
        list(model.parameters()) + list(classifier.parameters()),
        lr=float(reid_cfg['lr']),
    )
    ce_loss = torch.nn.CrossEntropyLoss()
    triplet_loss = torch.nn.TripletMarginLoss(margin=float(reid_cfg['margin']))

    best_loss = float('inf')
    output_dir = Path(reid_cfg['output_dir'])
    output_dir.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, int(reid_cfg['epochs']) + 1):
        model.train()
        total_loss = 0.0
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            embeddings = model(images)
            logits = classifier(embeddings)
            loss = ce_loss(logits, labels) + _batch_hard_triplet_loss(
                embeddings,
                labels,
                triplet_loss,
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())

        avg_loss = total_loss / max(1, len(loader))
        print(f'epoch={epoch} loss={avg_loss:.4f}')
        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save({'model': model.state_dict(), 'labels': dataset.label_to_id}, reid_cfg['checkpoint'])


def _batch_hard_triplet_loss(
    embeddings: torch.Tensor,
    labels: torch.Tensor,
    criterion: torch.nn.TripletMarginLoss,
) -> torch.Tensor:
    anchors = []
    positives = []
    negatives = []
    for idx, label in enumerate(labels):
        pos_indices = torch.where(labels == label)[0]
        neg_indices = torch.where(labels != label)[0]
        if len(pos_indices) < 2 or len(neg_indices) == 0:
            continue
        pos_idx = pos_indices[pos_indices != idx][0]
        neg_idx = neg_indices[0]
        anchors.append(embeddings[idx])
        positives.append(embeddings[pos_idx])
        negatives.append(embeddings[neg_idx])
    if not anchors:
        return embeddings.sum() * 0.0
    return criterion(torch.stack(anchors), torch.stack(positives), torch.stack(negatives))


if __name__ == '__main__':
    main()
