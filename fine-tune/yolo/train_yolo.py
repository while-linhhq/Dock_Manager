from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml
from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = REPO_ROOT / 'server'
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Fine-tune YOLO for boat detection.')
    parser.add_argument('--config', default='fine-tune/config.yaml')
    parser.add_argument('--model', default=None)
    parser.add_argument('--data', default=None)
    parser.add_argument('--epochs', type=int, default=None)
    parser.add_argument('--imgsz', type=int, default=None)
    parser.add_argument('--batch', type=int, default=None)
    parser.add_argument('--device', default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding='utf-8'))
    yolo_cfg = cfg['yolo']
    project_cfg = cfg.get('project', {})

    model_path = _resolve_model_path(args.model, yolo_cfg.get('base_model'))
    data_yaml = args.data or yolo_cfg['data_yaml']
    model = YOLO(model_path)
    model.train(
        data=data_yaml,
        epochs=args.epochs or int(yolo_cfg['epochs']),
        imgsz=args.imgsz or int(yolo_cfg['imgsz']),
        batch=args.batch or int(yolo_cfg['batch']),
        workers=int(yolo_cfg.get('workers', 4)),
        device=args.device or project_cfg.get('device', 'cpu'),
        project=yolo_cfg.get('project', 'fine-tune/runs/yolo'),
        name=yolo_cfg.get('name', 'boat-detector'),
    )


def _resolve_model_path(cli_model: str | None, config_model: str | None) -> str:
    for candidate in (cli_model, config_model, os.getenv('MODEL_PATH')):
        if candidate and str(candidate).strip():
            return str(candidate).strip()

    try:
        from app.core.config import settings
        from app.db.session import SessionLocal
        from app.repositories.port_config_repository import port_config_repo

        db = SessionLocal()
        try:
            for row in port_config_repo.get_all(db):
                if row.key == 'model_path' and str(row.value or '').strip():
                    return str(row.value).strip()
        finally:
            db.close()

        if str(settings.MODEL_PATH or '').strip():
            return str(settings.MODEL_PATH).strip()
    except Exception as err:
        raise RuntimeError(
            'Could not resolve YOLO model path. Set --model, yolo.base_model, '
            'MODEL_PATH, or configure model_path on the web settings page.'
        ) from err

    raise RuntimeError(
        'Could not resolve YOLO model path. Set --model, yolo.base_model, '
        'MODEL_PATH, or configure model_path on the web settings page.'
    )


if __name__ == '__main__':
    main()
