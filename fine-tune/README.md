# Fine-Tuning Framework

This folder is for offline training only. Runtime code loads the exported YOLO
weights through `MODEL_PATH` and the Re-ID embedding model through
`REID_EMBEDDING_MODEL_PATH`.

`fine-tune/yolo/train_yolo.py` resolves the base YOLO model in this order:
`--model`, `fine-tune/config.yaml` `yolo.base_model`, `MODEL_PATH`, then the
web/database `port_configs.model_path`.

## YOLO Boat Detection

Expected dataset:

```text
fine-tune/yolo/data/
  images/train/*.jpg
  images/val/*.jpg
  labels/train/*.txt
  labels/val/*.txt
```

Train:

```bash
cd server
conda run -n bason-dock python ../fine-tune/yolo/train_yolo.py --config ../fine-tune/config.yaml
```

## Ship Re-ID

Expected dataset:

```text
fine-tune/reid/data/
  train/{vessel_id}/*.jpg
  query/{vessel_id}/*.jpg
  gallery/{vessel_id}/*.jpg
```

Train and export:

```bash
cd server
conda run -n bason-dock python ../fine-tune/reid/train_reid.py --config ../fine-tune/config.yaml
conda run -n bason-dock python ../fine-tune/reid/export_onnx.py --config ../fine-tune/config.yaml
```
