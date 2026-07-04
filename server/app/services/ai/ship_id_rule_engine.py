"""
Singleton rule engine for ship ID OCR post-processing.

Holds compiled regex patterns, blacklist, and convert map in memory.
Reloaded from PostgreSQL every ~30 s by a background daemon thread.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATTERN = re.compile(r'([A-Z50]{2})[-\s]?(\d{4})')

# Numeric suffix of a ship ID split from prefix, e.g. 'TT-0000' -> '0000'.
_SUFFIX_RE = re.compile(r'-(\d+)$')


def _is_degenerate_number(candidate_id: str) -> bool:
    """True when the numeric suffix is all zeros (e.g. TT-0000, NC-00000).

    OCR on hull texture/shadow frequently hallucinates an all-zero number at
    high confidence. A real registration number is never all zeros, so reject
    it at the source before it can vote / auto-create a vessel.
    """
    match = _SUFFIX_RE.search(candidate_id)
    if not match:
        return False
    digits = match.group(1)
    return set(digits) == {'0'}


class ShipIdRuleEngine:
    def __init__(self) -> None:
        self._compiled_patterns: list[dict] = []
        self._blacklist: set[str] = set()
        self._convert_map: dict[str, str] = {}
        self._state_hash: str = ''
        self._lock = threading.RLock()

    # ── Public API ─────────────────────────────────────────────────────────

    def apply(self, candidate_id: str) -> Optional[str]:
        """
        Apply blacklist and convert map to a normalized candidate ID.
        Returns None if the ID is blacklisted, the corrected ID if in convert map,
        or the original ID unchanged.
        """
        normalized = candidate_id.strip().upper()
        if _is_degenerate_number(normalized):
            return None
        with self._lock:
            if normalized in self._blacklist:
                return None
            corrected = self._convert_map.get(normalized, normalized)
        # A convert-map target must also survive the degenerate check.
        if _is_degenerate_number(corrected):
            return None
        return corrected

    def extract_ship_ids(self, text: str) -> list[dict]:
        """
        Try each active pattern against text.
        Normalize prefix (5→S, 0→O), apply blacklist + convert map.
        Returns list of {id, confidence, raw_text}.
        """
        clean = text.upper().strip().replace(' ', '')
        results: list[dict] = []

        with self._lock:
            patterns = list(self._compiled_patterns)

        if not patterns:
            match = _DEFAULT_PATTERN.search(clean)
            if match:
                prefix = match.group(1).replace('5', 'S').replace('0', 'O')
                number = match.group(2)
                candidate = f'{prefix}-{number}'
                final_id = self.apply(candidate)
                if final_id is not None:
                    results.append({'id': final_id, 'confidence': 1.0, 'raw_text': text})
            return results

        for entry in patterns:
            compiled: re.Pattern = entry['pattern']
            match = compiled.search(clean)
            if not match:
                continue
            prefix = match.group(1).replace('5', 'S').replace('0', 'O')
            number = match.group(2)
            candidate = f'{prefix}-{number}'
            final_id = self.apply(candidate)
            if final_id is None:
                continue
            results.append({'id': final_id, 'confidence': 1.0, 'raw_text': text})

        return results

    # ── Reload from DB ─────────────────────────────────────────────────────

    def reload(self, db) -> bool:
        """
        Load rules from DB if state has changed since last reload.
        Returns True if rules were actually reloaded.
        """
        from app.repositories.ship_id_rule_repository import ship_id_rule_repo

        try:
            new_hash = ship_id_rule_repo.get_state_hash(db)
        except Exception as exc:
            logger.warning('ShipIdRuleEngine: could not read state hash: %s', exc)
            return False

        if new_hash == self._state_hash:
            return False

        try:
            raw_patterns = ship_id_rule_repo.get_active_patterns(db)
            raw_blacklist = ship_id_rule_repo.get_all_blacklist(db)
            raw_convert = ship_id_rule_repo.get_all_convert_map(db)
        except Exception as exc:
            logger.warning('ShipIdRuleEngine: reload failed: %s', exc)
            return False

        compiled: list[dict] = []
        for p in raw_patterns:
            try:
                compiled.append({'pattern': re.compile(p['pattern']), 'name': p['name']})
            except re.error as exc:
                logger.warning('ShipIdRuleEngine: invalid pattern %r skipped: %s', p['pattern'], exc)

        blacklist = {r['value'].strip().upper() for r in raw_blacklist}
        convert_map = {
            r['wrong_value'].strip().upper(): r['correct_value'].strip().upper()
            for r in raw_convert
        }

        with self._lock:
            self._compiled_patterns = compiled
            self._blacklist = blacklist
            self._convert_map = convert_map
            self._state_hash = new_hash

        logger.info(
            'ShipIdRuleEngine: reloaded %d patterns, %d blacklist, %d convert entries',
            len(compiled), len(blacklist), len(convert_map),
        )
        return True


# Module-level singleton shared by all camera pipelines
_engine: Optional[ShipIdRuleEngine] = None
_engine_lock = threading.Lock()
_daemon_started = False
_daemon_lock = threading.Lock()


def get_rule_engine() -> ShipIdRuleEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = ShipIdRuleEngine()
    return _engine


def start_rule_engine_daemon(interval_s: int = 30) -> None:
    """
    Start a background daemon thread that polls DB for rule changes every interval_s seconds.
    Call once from main.py lifespan. Safe to call multiple times (noop after first).
    """
    global _daemon_started
    with _daemon_lock:
        if _daemon_started:
            return
        _daemon_started = True

    engine = get_rule_engine()

    def _initial_load() -> None:
        from app.db.session import SessionLocal
        try:
            with SessionLocal() as db:
                engine.reload(db)
        except Exception as exc:
            logger.warning('ShipIdRuleEngine: initial load failed: %s', exc)

    def _loop() -> None:
        _initial_load()
        while True:
            time.sleep(interval_s)
            try:
                from app.db.session import SessionLocal
                with SessionLocal() as db:
                    engine.reload(db)
            except Exception as exc:
                logger.warning('ShipIdRuleEngine: daemon reload error: %s', exc)

    t = threading.Thread(target=_loop, name='ship-id-rule-engine-daemon', daemon=True)
    t.start()
    logger.info('ShipIdRuleEngine: daemon started (interval=%ds)', interval_s)
