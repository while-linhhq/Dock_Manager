from __future__ import annotations

import os
import struct
from pathlib import Path

from app.utils.media.faststart_mp4 import _iter_atoms


def get_mp4_video_codec_fourcc(path: str | Path) -> str | None:
    """
    Best-effort: return the first video sample entry type found in stsd (e.g. 'avc1', 'mp4v', 'hvc1').
    Only parses top-level atoms + moov payload; doesn't decode fragmented streams.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        with p.open('rb') as f:
            moov_atom = None
            for atom in _iter_atoms(f):
                if atom.typ == b'moov':
                    moov_atom = atom
                    break
            if moov_atom is None or moov_atom.size > 20_000_000:
                return None
            f.seek(moov_atom.offset, os.SEEK_SET)
            moov = f.read(moov_atom.size)

        idx = moov.find(b'stsd')
        if idx == -1:
            return None
        # stsd atom header is 4 (size) + 4 ('stsd') already in buffer somewhere; locate start of atom
        # 'stsd' occurs at offset idx, size field is 4 bytes before.
        if idx < 4:
            return None
        (atom_size,) = struct.unpack_from('>I', moov, idx - 4)
        atom_start = idx - 4
        atom_end = atom_start + atom_size
        if atom_end > len(moov):
            return None
        # stsd layout: size(4) type(4) version/flags(4) entry_count(4) then entries...
        base = atom_start + 8
        if base + 8 > atom_end:
            return None
        entry_count = struct.unpack_from('>I', moov, base + 4)[0]
        if entry_count < 1:
            return None
        entry_start = base + 8
        if entry_start + 8 > atom_end:
            return None
        # sample entry: size(4) + type(4)
        codec = moov[entry_start + 4 : entry_start + 8]
        if len(codec) != 4:
            return None
        return codec.decode('ascii', errors='ignore') or None
    except Exception:
        return None

