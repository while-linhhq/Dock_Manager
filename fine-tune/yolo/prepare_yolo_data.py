from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
YOLO_LINE_RE = re.compile(
    r'^(\d+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s*$'
)
COCO_BOAT_CLASS_ID = 8


@dataclass
class DatasetAudit:
    image_count: int = 0
    label_count: int = 0
    paired: int = 0
    exported: int = 0
    missing_label_images: int = 0
    orphan_labels: int = 0
    empty_labels: int = 0
    invalid_label_lines: int = 0
    bbox_issues: int = 0
    class_ids: set[int] = field(default_factory=set)
    unmatched_label_samples: list[str] = field(default_factory=list)
    unmatched_image_samples: list[str] = field(default_factory=list)
    filtered_small_boxes: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Validate Label Studio YOLO export and split into train/val folders.',
    )
    parser.add_argument(
        '--source',
        default='fine-tune/Dataset',
        help='Dataset root with images/ and labels/ (Label Studio export).',
    )
    parser.add_argument('--output', default='fine-tune/yolo/data')
    parser.add_argument('--val-ratio', type=float, default=0.2)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument(
        '--min-box-area',
        type=float,
        default=0.0,
        help='Drop boxes with normalized width*height below this threshold.',
    )
    parser.add_argument(
        '--require-label',
        action='store_true',
        default=True,
        help='Only export images that have a non-empty valid label (default).',
    )
    parser.add_argument(
        '--include-unlabeled',
        action='store_true',
        help='Also copy images without labels (empty label files).',
    )
    parser.add_argument(
        '--boost-stems-file',
        default='',
        help='Text file of image stems to oversample in train split (one per line).',
    )
    parser.add_argument(
        '--boost-factor',
        type=int,
        default=5,
        help='Extra copies in train for each boosted stem (default 5).',
    )
    parser.add_argument(
        '--pattern-boost-factor',
        type=int,
        default=0,
        help='Extra copies for --boost-pattern matches (0 = use --boost-factor).',
    )
    parser.add_argument(
        '--boost-pattern',
        action='append',
        default=[],
        help='Substring match on image stem to boost (repeatable).',
    )
    parser.add_argument(
        '--train-only-stems-file',
        default='',
        help='Stems forced into train split (never val), e.g. hard cases.',
    )
    return parser.parse_args()


def _load_class_id_map(source: Path) -> dict[int, int]:
    """
    Map raw Label Studio / COCO class ids to YOLO fine-tune indices (0-based).
    Single-class boat datasets always export class 0 (not COCO id 8).
    """
    classes_file = source / 'classes.txt'
    class_names: list[str] = []
    if classes_file.is_file():
        class_names = [
            line.strip()
            for line in classes_file.read_text(encoding='utf-8').splitlines()
            if line.strip()
        ]

    if len(class_names) == 1:
        return {0: 0, COCO_BOAT_CLASS_ID: 0}

    name_to_idx = {name.lower(): idx for idx, name in enumerate(class_names)}
    class_map: dict[int, int] = {idx: idx for idx in range(len(class_names))}

    notes_file = source / 'notes.json'
    if notes_file.is_file():
        notes = json.loads(notes_file.read_text(encoding='utf-8'))
        for category in notes.get('categories', []):
            raw_id = int(category['id'])
            raw_name = str(category.get('name', '')).lower()
            if raw_name in name_to_idx:
                class_map[raw_id] = name_to_idx[raw_name]

    if 'boat' in name_to_idx:
        class_map.setdefault(COCO_BOAT_CLASS_ID, name_to_idx['boat'])

    return class_map


def _format_yolo_line(class_id: int, x_center: float, y_center: float, width: float, height: float) -> str:
    return f'{class_id} {x_center} {y_center} {width} {height}'


def _collect_images(images_dir: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in images_dir.rglob('*'):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            out[path.stem] = path
    return out


def _collect_labels(labels_dir: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in labels_dir.glob('*.txt'):
        if path.name.lower() == 'classes.txt':
            continue
        out[path.stem] = path
    return out


def _label_image_stem(label_stem: str, images: dict[str, Path]) -> str | None:
    if label_stem in images:
        return label_stem
    if '-' in label_stem:
        suffix = label_stem.split('-', 1)[1]
        if suffix in images:
            return suffix
    return None


def _validate_label_file(
    label_path: Path,
    audit: DatasetAudit,
    *,
    min_box_area: float = 0.0,
    class_id_map: dict[int, int] | None = None,
) -> list[str] | None:
    text = label_path.read_text(encoding='utf-8').strip()
    if not text:
        audit.empty_labels += 1
        return None

    valid_lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = YOLO_LINE_RE.match(line)
        if not match:
            audit.invalid_label_lines += 1
            return None
        class_id = int(match.group(1))
        if class_id_map is not None:
            if class_id not in class_id_map:
                audit.invalid_label_lines += 1
                return None
            class_id = class_id_map[class_id]
        audit.class_ids.add(class_id)
        x_center, y_center, width, height = (
            float(match.group(i)) for i in range(2, 6)
        )
        if width <= 0 or height <= 0:
            audit.bbox_issues += 1
            return None
        if not all(0 <= v <= 1 for v in (x_center, y_center, width, height)):
            audit.bbox_issues += 1
            return None
        if width * height < min_box_area:
            audit.filtered_small_boxes += 1
            continue
        valid_lines.append(
            _format_yolo_line(class_id, x_center, y_center, width, height),
        )
    return valid_lines or None


def _pair_dataset(source: Path) -> tuple[dict[str, Path], dict[str, list[Path]], DatasetAudit]:
    images_dir = source / 'images'
    labels_dir = source / 'labels'
    if not images_dir.is_dir():
        raise FileNotFoundError(f'Missing images directory: {images_dir}')
    if not labels_dir.is_dir():
        raise FileNotFoundError(f'Missing labels directory: {labels_dir}')

    images = _collect_images(images_dir)
    labels = _collect_labels(labels_dir)
    audit = DatasetAudit(image_count=len(images), label_count=len(labels))

    image_to_labels: dict[str, list[Path]] = {}
    matched_image_stems: set[str] = set()

    for label_stem, label_path in labels.items():
        image_stem = _label_image_stem(label_stem, images)
        if image_stem is None:
            audit.orphan_labels += 1
            if len(audit.unmatched_label_samples) < 5:
                audit.unmatched_label_samples.append(label_stem)
            continue
        image_to_labels.setdefault(image_stem, []).append(label_path)
        matched_image_stems.add(image_stem)

    audit.paired = len(matched_image_stems)
    audit.missing_label_images = len(images) - len(matched_image_stems)
    for stem in sorted(set(images) - matched_image_stems)[:5]:
        audit.unmatched_image_samples.append(stem)

    return images, image_to_labels, audit


def _merge_label_files(
    label_paths: list[Path],
    audit: DatasetAudit,
    *,
    min_box_area: float = 0.0,
    class_id_map: dict[int, int] | None = None,
) -> list[str] | None:
    merged: list[str] = []
    seen: set[str] = set()
    for label_path in label_paths:
        lines = _validate_label_file(
            label_path,
            audit,
            min_box_area=min_box_area,
            class_id_map=class_id_map,
        )
        if not lines:
            continue
        for line in lines:
            if line not in seen:
                seen.add(line)
                merged.append(line)
    return merged or None


def _load_stem_set(path: str) -> set[str]:
    if not path:
        return set()
    file_path = Path(path)
    if not file_path.is_file():
        return set()
    return {
        line.strip()
        for line in file_path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    }


def _boost_count(
    image_stem: str,
    *,
    boost_stems: set[str],
    stem_boost_factor: int,
    boost_patterns: list[str],
    pattern_boost_factor: int,
) -> int:
    extra = 0
    if image_stem in boost_stems:
        extra = max(extra, stem_boost_factor)
    for pattern in boost_patterns:
        if pattern and pattern in image_stem:
            extra = max(extra, pattern_boost_factor)
    return extra


def _print_audit(audit: DatasetAudit) -> None:
    print('=== Dataset audit ===')
    print(f'  images:              {audit.image_count}')
    print(f'  labels:              {audit.label_count}')
    print(f'  paired (image↔label): {audit.paired}')
    print(f'  images w/o label:    {audit.missing_label_images}')
    print(f'  orphan labels:       {audit.orphan_labels}')
    print(f'  empty labels:        {audit.empty_labels}')
    print(f'  invalid label lines: {audit.invalid_label_lines}')
    print(f'  bbox issues:         {audit.bbox_issues}')
    print(f'  filtered small boxes:{audit.filtered_small_boxes}')
    print(f'  class ids:           {sorted(audit.class_ids) or "(none)"}')
    if audit.unmatched_label_samples:
        print(f'  sample orphan labels: {audit.unmatched_label_samples}')
    if audit.unmatched_image_samples:
        print(f'  sample unlabeled:     {audit.unmatched_image_samples}')


def main() -> None:
    args = parse_args()
    source = Path(args.source)
    output = Path(args.output)
    require_label = args.require_label and not args.include_unlabeled
    min_box_area = max(0.0, float(args.min_box_area))
    class_id_map = _load_class_id_map(source)
    boost_stems = _load_stem_set(args.boost_stems_file)
    train_only_stems = _load_stem_set(args.train_only_stems_file)
    stem_boost_factor = max(1, int(args.boost_factor))
    pattern_boost_factor = int(args.pattern_boost_factor)
    if pattern_boost_factor <= 0:
        pattern_boost_factor = stem_boost_factor
    boost_patterns = list(args.boost_pattern or [])

    images, image_to_labels, audit = _pair_dataset(source)
    _print_audit(audit)

    if output.exists():
        shutil.rmtree(output)
    for split in ('train', 'val'):
        (output / 'images' / split).mkdir(parents=True, exist_ok=True)
        (output / 'labels' / split).mkdir(parents=True, exist_ok=True)

    export_items: list[tuple[Path, list[str] | None, str]] = []

    for image_stem, image_path in sorted(images.items()):
        label_paths = image_to_labels.get(image_stem, [])
        label_lines: list[str] | None = None
        if label_paths:
            label_lines = _merge_label_files(
                label_paths,
                audit,
                min_box_area=min_box_area,
                class_id_map=class_id_map,
            )
        if require_label and not label_lines:
            continue
        export_items.append((image_path, label_lines, image_stem))

    rng = random.Random(args.seed)
    regular_items: list[tuple[Path, list[str] | None, str]] = []
    forced_train: list[tuple[Path, list[str] | None, str]] = []
    for item in export_items:
        image_stem = item[2]
        if image_stem in train_only_stems or image_stem in boost_stems:
            forced_train.append(item)
        else:
            regular_items.append(item)

    rng.shuffle(regular_items)
    val_count = int(len(regular_items) * max(0.0, min(float(args.val_ratio), 0.9)))
    val_set = set(range(val_count))

    train_n = 0
    val_n = 0
    boosted_copies = 0

    def _write_sample(
        image_path: Path,
        label_lines: list[str] | None,
        image_stem: str,
        split: str,
        *,
        copy_suffix: str = '',
    ) -> None:
        nonlocal train_n, val_n, boosted_copies
        out_name = image_path.name
        out_stem = image_stem
        if copy_suffix:
            out_stem = f'{image_stem}__boost{copy_suffix}'
            out_name = f'{out_stem}{image_path.suffix}'
            boosted_copies += 1
        shutil.copy2(image_path, output / 'images' / split / out_name)
        label_content = '\n'.join(label_lines) + '\n' if label_lines else ''
        (output / 'labels' / split / f'{out_stem}.txt').write_text(
            label_content,
            encoding='utf-8',
        )
        if split == 'val':
            val_n += 1
        else:
            train_n += 1

    for idx, (image_path, label_lines, image_stem) in enumerate(regular_items):
        split = 'val' if idx in val_set else 'train'
        _write_sample(image_path, label_lines, image_stem, split)
        if split == 'train':
            extra = _boost_count(
                image_stem,
                boost_stems=boost_stems,
                stem_boost_factor=stem_boost_factor,
                boost_patterns=boost_patterns,
                pattern_boost_factor=pattern_boost_factor,
            )
            for copy_idx in range(extra):
                _write_sample(
                    image_path,
                    label_lines,
                    image_stem,
                    'train',
                    copy_suffix=str(copy_idx + 1),
                )

    for image_path, label_lines, image_stem in forced_train:
        _write_sample(image_path, label_lines, image_stem, 'train')
        extra = _boost_count(
            image_stem,
            boost_stems=boost_stems,
            stem_boost_factor=stem_boost_factor,
            boost_patterns=boost_patterns,
            pattern_boost_factor=pattern_boost_factor,
        )
        for copy_idx in range(extra):
            _write_sample(
                image_path,
                label_lines,
                image_stem,
                'train',
                copy_suffix=str(copy_idx + 1),
            )

    audit.exported = len(export_items)
    print('=== Export ===')
    print(f'  output:   {output.resolve()}')
    print(f'  total:    {audit.exported}')
    print(f'  train:    {train_n}')
    print(f'  val:      {val_n}')
    print(f'  boosted:  {boosted_copies}')
    if boost_stems:
        print(f'  boost stems file: {args.boost_stems_file} ({len(boost_stems)} stems)')
    if boost_patterns:
        print(
            f'  boost patterns:   {boost_patterns} '
            f'(stem x{stem_boost_factor}, pattern x{pattern_boost_factor})',
        )
    if train_only_stems:
        print(f'  train-only stems: {len(train_only_stems)}')
    if audit.exported == 0:
        raise SystemExit('No valid samples exported — check labels and pairing.')
    if audit.class_ids - {0}:
        print(
            f'  WARNING: unexpected class ids {sorted(audit.class_ids - {0})}; '
            'expected single class 0=boat',
        )


if __name__ == '__main__':
    main()
