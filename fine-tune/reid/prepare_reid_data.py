from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Split vessel crop folders into train/query/gallery for Re-ID.'
    )
    parser.add_argument('--source', required=True, help='Folder shaped as {vessel_id}/*.jpg')
    parser.add_argument('--output', default='fine-tune/reid/data')
    parser.add_argument('--seed', type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output = Path(args.output)
    rng = random.Random(args.seed)

    for split in ('train', 'query', 'gallery'):
        (output / split).mkdir(parents=True, exist_ok=True)

    for vessel_dir in sorted(path for path in source.iterdir() if path.is_dir()):
        crops = [
            path for path in vessel_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
        if len(crops) < 3:
            continue
        rng.shuffle(crops)
        query = crops[:1]
        gallery = crops[1:2]
        train = crops[2:]
        for split, paths in {'query': query, 'gallery': gallery, 'train': train}.items():
            target_dir = output / split / vessel_dir.name
            target_dir.mkdir(parents=True, exist_ok=True)
            for crop in paths:
                shutil.copy2(crop, target_dir / crop.name)

    print(f'Re-ID data prepared under {output}')


if __name__ == '__main__':
    main()
