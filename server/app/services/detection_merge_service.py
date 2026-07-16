"""Post-hoc detection merge service.

After the pipeline creates a detection, call absorb_contained() to find any
older detections of the same vessel that belong to the SAME physical berthing
visit — either because their time windows overlap, or because the gap between
them is small enough that they are just fragments of one visit whose track was
lost and re-acquired — absorb them (soft-delete their UNPAID invoices and
themselves), and return the winner's id.

The winner is always the detection with the longest effective duration
(berth_out − berth_in, fallback end_time − berth_in). The winner's berth window
is then widened to span the whole coalesced cluster (earliest berth_in, latest
berth_out) so the surviving detection reflects the full visit.

TWO MERGE CRITERIA (either one triggers a merge):
  1. Overlap: the two windows literally intersect (e.g. two cameras see the
     same boat at the same time).
  2. Gap: the boat left the frame / lost track and re-appeared shortly after.
     Empirically (see 7/6-7/8 gap histogram) a lost-and-reacquired track
     re-appears within ~30 min, whereas a boat that truly departed does not
     come back for 40-60 min. So a gap below `berth_merge_gap_sec` (default
     1800s = 30 min) means "same visit, stitch it"; a larger gap means "a real
     separate visit, keep both".

Both `berth_merge_gap_sec` and `detection_merge_window_hours` (the coarse
candidate pre-filter) are read live from port_configs so they can be tuned from
the UI without a restart.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.detection_repository import detection_repo
from app.services.ship_id_utils import is_unknown_ship_id

_log = logging.getLogger(__name__)

# Fallbacks used only when the port_config row is missing/unparseable.
_DEFAULT_MERGE_GAP_SEC = 1800.0   # 30 min — bottom of the 30-40' valley
_DEFAULT_WINDOW_HOURS = 2.0       # coarse candidate pre-filter half-width
_DEFAULT_SKIP_UNKNOWN = True      # tàu chưa định danh: KHÔNG gộp


def _effective_end(det) -> datetime | None:
    """berth_out_time nếu có, fallback end_time (track mất giữa chừng).
    Normalize sang tz-aware UTC để tránh lỗi subtract naive/aware."""
    raw = det.berth_out_time or det.end_time
    if raw is None:
        return None
    if raw.tzinfo is None:
        return raw.replace(tzinfo=timezone.utc)
    return raw


def _berth_start(det) -> datetime | None:
    raw = det.berth_in_time
    if raw is None:
        return None
    if raw.tzinfo is None:
        return raw.replace(tzinfo=timezone.utc)
    return raw


def _effective_duration(det) -> float:
    start, end = _berth_start(det), _effective_end(det)
    if start is None or end is None:
        return 0.0
    return max(0.0, (end - start).total_seconds())


def _windows_overlap(a, b) -> bool:
    """True khi hai cửa sổ neo [berth_in, effective_end] thực sự giao nhau."""
    a_start, a_end = _berth_start(a), _effective_end(a)
    b_start, b_end = _berth_start(b), _effective_end(b)
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return False
    return a_start < b_end and b_start < a_end


def _gap_seconds(a, b) -> float | None:
    """Khoảng TRỐNG (giây) giữa hai lượt: từ lúc lượt trước rời (effective_end)
    tới lúc lượt sau đến (berth_in). Chồng lấn → 0. None nếu thiếu mốc.

    Đây là tín hiệu 'tàu vắng mặt bao lâu' — phân biệt track-chết-nối-lại
    (gap ngắn) với rời-bến-thật-rồi-quay-lại (gap dài). KHÔNG dùng
    berth_out_source làm hàng rào vì tàu rời ở mép camera cũng fallback
    last_seen (rời thật mà vẫn thiếu OUT crossing) — chỉ có gap phân biệt được.
    """
    a_start, a_end = _berth_start(a), _effective_end(a)
    b_start, b_end = _berth_start(b), _effective_end(b)
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return None
    if a_end <= b_start:            # a trước b
        return (b_start - a_end).total_seconds()
    if b_end <= a_start:            # b trước a
        return (a_start - b_end).total_seconds()
    return 0.0                      # chồng lấn


def _cfg_float(db: Session, key: str, fallback: float) -> float:
    """Đọc 1 giá trị float từ port_configs (live), fallback khi thiếu/hỏng."""
    try:
        from app.repositories.port_config_repository import port_config_repo

        row = port_config_repo.get_by_key(db, key)
        raw = str(row.value) if row is not None and row.value is not None else ''
        return float(raw.strip())
    except Exception:
        return float(fallback)


def _merge_gap_sec(db: Session) -> float:
    return _cfg_float(
        db,
        'berth_merge_gap_sec',
        float(getattr(settings, 'BERTH_MERGE_GAP_SEC', _DEFAULT_MERGE_GAP_SEC)),
    )


def _window_hours(db: Session) -> float:
    return _cfg_float(
        db,
        'detection_merge_window_hours',
        float(getattr(settings, 'DETECTION_MERGE_WINDOW_HOURS', _DEFAULT_WINDOW_HOURS)),
    )


def _cfg_bool(db: Session, key: str, fallback: bool) -> bool:
    """Đọc 1 giá trị bool từ port_configs (live), fallback khi thiếu/hỏng."""
    try:
        from app.repositories.port_config_repository import port_config_repo

        row = port_config_repo.get_by_key(db, key)
        raw = str(row.value).strip().lower() if row is not None and row.value is not None else ''
        if raw in ('true', '1', 'yes', 'on'):
            return True
        if raw in ('false', '0', 'no', 'off'):
            return False
        return bool(fallback)
    except Exception:
        return bool(fallback)


def _skip_unknown(db: Session) -> bool:
    return _cfg_bool(
        db,
        'berth_merge_skip_unknown',
        bool(getattr(settings, 'BERTH_MERGE_SKIP_UNKNOWN', _DEFAULT_SKIP_UNKNOWN)),
    )


def _detection_ship_id(det) -> str:
    """ship_id của tàu gắn với detection (qua vessel). '' nếu không có vessel."""
    vessel = getattr(det, 'vessel', None)
    if vessel is None:
        return ''
    return str(getattr(vessel, 'ship_id', '') or '')


def _detection_is_unknown(det) -> bool:
    """Detection chưa định danh tàu (vessel là UNKNOWN, hoặc chưa có vessel).

    Tàu UNKNOWN đều trỏ về CÙNG một vessel 'UNKNOWN' → nếu gộp theo vessel_id sẽ
    trộn nhiều con tàu khác nhau thành một. Phải loại khỏi coalesce cho tới khi
    Zalo bot xác nhận danh tính (reassign sang vessel thật).
    """
    return is_unknown_ship_id(_detection_ship_id(det))


def _adjacent_linked(a, b, gap_sec: float) -> bool:
    """Hai lượt KỀ nhau thuộc cùng một cụm? True khi chồng lấn HOẶC gap < ngưỡng.

    Chỉ dùng cho hai detection LIỀN KỀ trên trục thời gian (single-linkage).
    KHÔNG so trực tiếp new_det với mọi ứng viên — vì một chuỗi mảnh có thể
    trải dài hơn gap_sec (ví dụ 00:11 → 00:55 = 44 phút) trong khi mỗi khoảng
    kề chỉ vài phút. Nối bắc cầu qua từng khoảng kề mới gom trọn được cụm.
    """
    if _windows_overlap(a, b):
        return True
    gap = _gap_seconds(a, b)
    return gap is not None and gap < gap_sec


def _out_source(det) -> str:
    """berth_out_source của detection ('crossing' / 'last_seen' / '')."""
    return str(getattr(det, 'berth_out_source', '') or '')


def _in_source(det) -> str:
    """berth_in_source của detection ('crossing' / 'inferred' / '')."""
    return str(getattr(det, 'berth_in_source', '') or '')


def _cluster_containing_new(new_det, candidates, gap_sec: float) -> list:
    """Single-linkage clustering theo trục thời gian; trả về cụm chứa new_det.

    Sort tất cả detection (new_det + ứng viên hợp lệ) theo berth_in, rồi quét
    tuyến tính: nối detection hiện tại vào cụm đang mở nếu nó KỀ (overlap/gap<
    ngưỡng) với BẤT KỲ detection nào đã trong cụm — dùng effective_end lớn nhất
    của cụm làm mốc so, để một mảnh dài che khoảng trống cho mảnh sau. Khi gặp
    detection không nối được, đóng cụm cũ, mở cụm mới. Cuối cùng trả về đúng cụm
    chứa new_det.

    HÀNG RÀO OUT-CROSSING (bất đối xứng): nếu mảnh đang định biên cụm (mảnh có
    effective_end xa nhất) rời bằng OUT crossing THẬT (berth_out_source=
    'crossing'), KHÔNG nối mảnh sau vào — dù gap nhỏ. Lý do: OUT crossing là
    bằng chứng CỨNG tàu đã rời bến; mảnh sau là một LƯỢT MỚI, không phải track
    bị đứt-nối-lại. (Ngược lại, thiếu OUT crossing = 'last_seen' KHÔNG chứng minh
    tàu còn ở bến — tàu rời ở mép camera cũng fallback last_seen — nên last_seen
    vẫn cho nối, để gap tự phân biệt track-chết với rời-thật-quay-lại. Chỉ dùng
    SỰ HIỆN DIỆN của crossing làm hàng rào, không dùng sự VẮNG MẶT.)
    """
    pool = [new_det] + [
        c for c in candidates
        if c.berth_in_time is not None and _berth_start(c) is not None
    ]
    # Sort theo berth_in (mốc bắt đầu); tie-break bằng effective_end.
    pool.sort(key=lambda d: (_berth_start(d), _effective_end(d) or _berth_start(d)))

    clusters: list[list] = []
    current: list = []
    current_end = None  # effective_end lớn nhất trong cụm đang mở
    current_end_src = ''  # berth_out_source của mảnh định biên current_end

    for det in pool:
        d_start = _berth_start(det)
        d_end = _effective_end(det)
        if not current:
            current = [det]
            current_end = d_end
            current_end_src = _out_source(det)
            continue
        # Gap giữa mốc kết thúc xa nhất của cụm và mốc bắt đầu det hiện tại.
        # <=0 nghĩa là chồng lấn/liền kề.
        if current_end is None or d_start is None:
            linked = False
        else:
            gap = (d_start - current_end).total_seconds()
            linked = gap < gap_sec  # gap âm (overlap) hoặc < ngưỡng → nối
            # Hàng rào: biên cụm rời bằng OUT crossing thật → không nối lượt sau.
            # Overlap (gap<=0) vẫn nối vì đó là 2 camera thấy cùng lúc, không phải
            # 2 lượt tách biệt.
            if linked and gap > 0 and current_end_src == 'crossing':
                linked = False
        if linked:
            current.append(det)
            if d_end is not None and (current_end is None or d_end > current_end):
                current_end = d_end
                current_end_src = _out_source(det)
        else:
            clusters.append(current)
            current = [det]
            current_end = d_end
            current_end_src = _out_source(det)
    if current:
        clusters.append(current)

    for cl in clusters:
        if any(d.id == new_det.id for d in cl):
            return cl
    return [new_det]


def absorb_contained(db: Session, detection_id: int) -> int:
    """Absorb detections of the same vessel that belong to the same berthing
    visit as the new detection (overlapping OR within `berth_merge_gap_sec`).

    Candidate chỉ cần có berth_in_time (berth_out_time có thể NULL — dùng
    end_time fallback). Detection đã accepted (is_accepted=True) được repo
    query loại ở tầng DB.

    Returns:
        The winner's detection id (may differ from detection_id if an older
        detection turns out to have a longer effective window). Winner's berth
        window is widened to span the whole coalesced cluster.
    """
    new_det = detection_repo.get(db, detection_id)
    if new_det is None:
        _log.warning('detection_merge: detection %s not found, skipping', detection_id)
        return detection_id

    if new_det.berth_in_time is None or new_det.berth_out_time is None:
        return detection_id

    # Ngoại lệ UNKNOWN: tàu chưa định danh KHÔNG gộp. Mọi detection UNKNOWN trỏ
    # về CÙNG một vessel 'UNKNOWN', nên coalesce theo vessel_id sẽ trộn nhiều con
    # tàu khác nhau thành một lượt sai. Giữ nguyên từng detection cho tới khi
    # Zalo bot xác nhận ship_id (reassign sang vessel thật) → lúc đó mới gộp lại.
    if _skip_unknown(db) and _detection_is_unknown(new_det):
        return detection_id

    gap_sec = _merge_gap_sec(db)
    window_hours = _window_hours(db)
    # Lưới lọc ứng viên phải RỘNG hơn ngưỡng gộp, nếu không sẽ cắt oan ứng viên
    # hợp lệ (candidate cách new_det gần bằng gap_sec vẫn phải lọt lưới).
    effective_window_hours = max(window_hours, (gap_sec / 3600.0) + window_hours)

    candidates = detection_repo.get_overlapping_by_vessel(
        db,
        vessel_id=new_det.vessel_id,
        berth_in=new_det.berth_in_time,
        berth_out=new_det.berth_out_time,
        exclude_id=new_det.id,
        window_hours=effective_window_hours,
    )

    # Gom cụm bắc cầu (single-linkage) theo trục thời gian: nối các mảnh KỀ nhau
    # khi khoảng trống kề < berth_merge_gap_sec (hoặc chồng lấn). Chỉ giữ cụm
    # chứa new_det. Bắc cầu qua từng khoảng kề mới gom trọn được một lượt neo bị
    # vỡ nhiều mảnh mà tổng span dài hơn ngưỡng (ví dụ 00:11→00:55 = 44 phút với
    # mỗi khoảng kề chỉ vài phút). Bộ lọc window ở repo chỉ là lưới thô.
    pool = _cluster_containing_new(new_det, candidates, gap_sec)

    winner = max(pool, key=_effective_duration)

    now = datetime.now(timezone.utc)

    # Coalesce: winner span trọn cụm — berth_in sớm nhất, berth_out muộn nhất.
    starts = [s for s in (_berth_start(d) for d in pool) if s is not None]
    ends = [e for e in (_effective_end(d) for d in pool) if e is not None]
    cluster_start = min(starts) if starts else None
    # cluster_end: mốc RỜI của cụm. OUT crossing là bằng chứng CỨNG tàu đã rời
    # bến — một mảnh 'last_seen' MUỘN HƠN (đuôi track, hoặc re-touch camera khác
    # vài giây sau khi vạch OUT đã nổ) KHÔNG được kéo berth_out quá mốc crossing
    # thật, cũng KHÔNG được xoá provenance 'crossing'. Nên: nếu cụm có BẤT KỲ
    # mảnh 'crossing', cluster_end = mốc crossing MUỘN NHẤT (src='crossing'),
    # mọi last_seen sau đó bị bỏ. Chỉ khi cụm KHÔNG có crossing nào mới dùng
    # effective_end muộn nhất (last_seen). Đây chính là lỗi det 2004 (SG-6898,
    # 7/8): mảnh đuôi last_seen 06:33:33 từng đè OUT crossing thật 06:33:16 →
    # cột berth_out_source bị lật 'crossing'→'last_seen', dwell cộng dôi 17s, và
    # hàng rào OUT-crossing incremental (chống nối oan lượt kế) mất hiệu lực.
    #
    # Lưu ý phạm vi: chỉ chi phối phép NỚI cửa sổ (không kéo berth_out VƯỢT mốc
    # crossing). KHÔNG tự động RÚT ngắn berth_out của winner khi winner rời bằng
    # last_seen mà một mảnh KHÁC có crossing SỚM hơn — trường hợp đó không xuất
    # hiện trong dữ liệu thật và rút ngắn berth_out có rủi ro thiếu cước.
    crossing_ends = [
        e
        for e in (
            _effective_end(d) for d in pool if _out_source(d) == 'crossing'
        )
        if e is not None
    ]
    if crossing_ends:
        cluster_end = max(crossing_ends)
        cluster_end_src = 'crossing'
    else:
        cluster_end = max(ends) if ends else None
        cluster_end_src = ''
        if cluster_end is not None:
            for d in pool:
                de = _effective_end(d)
                if de is not None and de == cluster_end:
                    cluster_end_src = _out_source(d)
                    break
    # Detection cấp cluster_start (mốc vào sớm nhất) — dùng để propagate
    # berth_in_source cho winner (đối xứng cluster_end_src). Ưu tiên 'crossing'
    # để mốc IN thật thắng 'inferred' khi nhiều mảnh cùng mốc start.
    cluster_start_src = ''
    if cluster_start is not None:
        for d in pool:
            ds = _berth_start(d)
            if ds is not None and ds == cluster_start:
                if _in_source(d) == 'crossing':
                    cluster_start_src = 'crossing'
                    break
                if not cluster_start_src:
                    cluster_start_src = _in_source(d)

    for det in pool:
        if det.id == winner.id:
            continue

        for inv in list(det.invoices):
            if inv.payment_status == 'UNPAID' and inv.deleted_at is None:
                inv.deleted_at = now

        detection_repo.soft_delete(db, det.id)

        _log.info(
            'detection_merge: absorbed detection %s (dur=%.1fs) into winner %s '
            '(dur=%.1fs, gap_sec_cfg=%.0f)',
            det.id,
            _effective_duration(det),
            winner.id,
            _effective_duration(winner),
            gap_sec,
        )

    # Mở rộng cửa sổ winner để phản ánh toàn bộ lượt neo (chỉ khi có mảnh khác).
    if len(pool) > 1:
        w_start = _berth_start(winner)
        w_end = _effective_end(winner)
        if cluster_start is not None and (w_start is None or cluster_start < w_start):
            winner.berth_in_time = cluster_start
            # Propagate source của mốc vào sớm nhất (đối xứng cluster_end_src).
            # Nếu mảnh cấp cluster_start vào bằng IN crossing thật, winner mang
            # src='crossing'; nếu suy diễn thì 'inferred'. Giữ đúng semantics IN.
            if cluster_start_src:
                winner.berth_in_source = cluster_start_src
        crossing_caps_last_seen = (
            cluster_end_src == 'crossing' and _out_source(winner) != 'crossing'
        )
        if cluster_end is not None and (w_end is None or cluster_end > w_end or crossing_caps_last_seen):
            # OUT crossing là hard evidence. Nó có thể cắt ngắn mốc last_seen
            # muộn hơn; không để fragment crossing bị xóa rồi mất hàng rào OUT.
            if winner.berth_out_time is not None:
                winner.berth_out_time = cluster_end
                if cluster_end_src:
                    winner.berth_out_source = cluster_end_src

    db.commit()

    return winner.id
