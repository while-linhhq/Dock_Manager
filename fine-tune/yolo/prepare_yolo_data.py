from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Create a YOLO dataset skeleton from reviewed boat images.'
    )
    parser.add_argument('--source-images', required=True)
    parser.add_argument('--source-labels', default=None)
    parser.add_argument('--output', default='fine-tune/yolo/data')
    parser.add_argument('--val-ratio', type=float, default=0.2)
    parser.add_argument('--seed', type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_images = Path(args.source_images)
    source_labels = Path(args.source_labels) if args.source_labels else None
    output = Path(args.output)
    images = [
        path for path in source_images.rglob('*')
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    random.Random(args.seed).shuffle(images)
    val_count = int(len(images) * max(0.0, min(args.val_ratio, 0.9)))
    val_set = set(images[:val_count])

    for split in ('train', 'val'):
        (output / 'images' / split).mkdir(parents=True, exist_ok=True)
        (output / 'labels' / split).mkdir(parents=True, exist_ok=True)

    for image_path in images:
        split = 'val' if image_path in val_set else 'train'
        target_image = output / 'images' / split / image_path.name
        shutil.copy2(image_path, target_image)

        target_label = output / 'labels' / split / f'{image_path.stem}.txt'
        if source_labels:
            label_path = source_labels / f'{image_path.stem}.txt'
            if label_path.exists():
                shutil.copy2(label_path, target_label)
                continue
        target_label.write_text('', encoding='utf-8')

    print(f'Prepared {len(images)} images under {output}')
    print('Empty label files mean the image must be reviewed/annotated before training.')


if __name__ == '__main__':
    main()
