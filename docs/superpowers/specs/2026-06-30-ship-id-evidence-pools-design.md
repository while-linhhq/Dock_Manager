# Ship ID Evidence Pools Design

## Context

Current final `ship_id` logic can choose the wrong vessel ID because OCR and visual embedding evidence can be mixed into one winner path. Visual embedding may accumulate repeated scores and beat correct OCR; hard-prioritizing OCR can also be wrong when OCR has one bad read and embedding is stable.

Goal: split OCR and embedding evidence into separate pools, then decide final `ship_id` using existing runtime config only. No new tuning keys.

## Configuration

Use existing `port_configs` keys:

- `detection_confidence_threshold`: minimum OCR pool total confidence to accept OCR winner.
- `visual_match_threshold`: minimum embedding average score when OCR is already valid.
- `visual_no_ocr_match_threshold`: minimum embedding average score when OCR is not valid.
- `visual_conflict_threshold`: embedding average score needed to override a conflicting valid OCR winner.

## Decision Rules

Pools:

- OCR pool groups OCR confidence by `ship_id` and picks highest `total_score`.
- Embedding pool groups visual match score by `ship_id` and picks highest `avg_score` / `total_score`.

Decision:

1. OCR valid + embedding valid + same `ship_id` => final consensus.
2. OCR valid + embedding invalid => final OCR.
3. OCR invalid + embedding valid => final embedding.
4. OCR valid + embedding valid + conflict:
   - if embedding avg score >= `visual_conflict_threshold` => final embedding.
   - else if OCR has repeated evidence (`count >= 2`) => final OCR.
   - else => final embedding.
5. Neither valid => no final.

Locking:

- `ship_id_locked=True` only when resolver returns `state='final'` and value stays stable for `ship_id_lock_stable_sec`.
- Locked tracks still skip OCR/visual votes.

## Architecture

`server/app/services/ai/ship_id_evidence.py` owns:

- `ShipIdEvidenceConfig`
- `EvidencePool`
- `ShipIdEvidence`
- `ShipIdDecision`

`BoatTracker` owns per-track evidence and receives existing config thresholds from pipeline runtime config.

`PerCameraPipeline` records visual top hit into embedding pool and no longer reports visual results as OCR evidence.

## Testing

Focused tests cover:

1. OCR winner uses `detection_confidence_threshold`.
2. Embedding winner uses `visual_no_ocr_match_threshold` when no valid OCR exists.
3. OCR + embedding agreement returns consensus.
4. Single wrong OCR loses to valid embedding.
5. Repeated OCR beats conflicting embedding below `visual_conflict_threshold`.
6. Embedding above `visual_conflict_threshold` beats conflicting OCR.
7. Existing lock and zone-gated vote tests still pass.

Run:

```bash
pytest server/app/tests/test_ship_id_lock.py server/app/tests/test_ship_id_evidence.py server/app/tests/test_zone_gated_vote.py -q
```
