from __future__ import annotations

import argparse
from pathlib import Path

import torch
import yaml

from model import ReidEmbeddingNet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Export Re-ID embedding model to ONNX.')
    parser.add_argument('--config', default='fine-tune/config.yaml')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding='utf-8'))
    reid_cfg = cfg['reid']
    model = ReidEmbeddingNet(int(reid_cfg['embedding_dim']))
    checkpoint = torch.load(reid_cfg['checkpoint'], map_location='cpu', weights_only=True)
    model.load_state_dict(checkpoint['model'])
    model.eval()

    output_path = Path(reid_cfg['onnx_output'])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 3, int(reid_cfg['image_size']), int(reid_cfg['image_size']))
    torch.onnx.export(
        model,
        dummy,
        output_path,
        input_names=['images'],
        output_names=['embeddings'],
        dynamic_axes={'images': {0: 'batch'}, 'embeddings': {0: 'batch'}},
        opset_version=17,
    )
    print(f'Exported {output_path}')


if __name__ == '__main__':
    main()
