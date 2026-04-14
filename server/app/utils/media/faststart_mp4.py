from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Mp4Atom:
    typ: bytes  # 4 bytes
    offset: int
    size: int
    header_size: int


def _read_atom(f) -> Mp4Atom | None:
    start = f.tell()
    hdr = f.read(8)
    if len(hdr) < 8:
        return None
    size32, typ = struct.unpack('>I4s', hdr)
    header_size = 8
    if size32 == 1:
        ext = f.read(8)
        if len(ext) < 8:
            return None
        (size64,) = struct.unpack('>Q', ext)
        size = int(size64)
        header_size = 16
    elif size32 == 0:
        # atom extends to EOF
        cur = f.tell()
        f.seek(0, os.SEEK_END)
        end = f.tell()
        f.seek(cur, os.SEEK_SET)
        size = end - start
    else:
        size = int(size32)
    if size < header_size:
        return None
    return Mp4Atom(typ=typ, offset=start, size=size, header_size=header_size)


def _iter_atoms(f):
    f.seek(0, os.SEEK_SET)
    while True:
        atom = _read_atom(f)
        if atom is None:
            break
        yield atom
        f.seek(atom.offset + atom.size, os.SEEK_SET)


def _patch_chunk_offsets(moov: bytes, shift: int) -> bytes:
    """
    Patch stco/co64 chunk offsets inside moov atom by +shift.
    This follows the qtfaststart approach (best-effort, assumes non-fragmented MP4).
    """
    data = bytearray(moov)

    def _find_all(pattern: bytes):
        i = 0
        while True:
            i = data.find(pattern, i)
            if i == -1:
                return
            yield i
            i += 4

    for off in _find_all(b'stco'):
        # stco atom: size(4) + 'stco'(4) + version/flags(4) + entry_count(4) + entries(4*count)
        try:
            atom_size = struct.unpack_from('>I', data, off - 4)[0]
            if atom_size < 16:
                continue
            base = off + 4
            entry_count = struct.unpack_from('>I', data, base + 8)[0]
            entries = base + 12
            for i in range(entry_count):
                pos = entries + i * 4
                (val,) = struct.unpack_from('>I', data, pos)
                struct.pack_into('>I', data, pos, (val + shift) & 0xFFFFFFFF)
        except Exception:
            continue

    for off in _find_all(b'co64'):
        # co64 atom: size(4) + 'co64'(4) + version/flags(4) + entry_count(4) + entries(8*count)
        try:
            atom_size = struct.unpack_from('>I', data, off - 4)[0]
            if atom_size < 16:
                continue
            base = off + 4
            entry_count = struct.unpack_from('>I', data, base + 8)[0]
            entries = base + 12
            for i in range(entry_count):
                pos = entries + i * 8
                (val,) = struct.unpack_from('>Q', data, pos)
                struct.pack_into('>Q', data, pos, val + shift)
        except Exception:
            continue

    return bytes(data)


def faststart_to_file(src_path: str | Path, dst_path: str | Path) -> bool:
    """
    Move moov atom before mdat and patch chunk offsets.
    Returns True if conversion happened; False if already faststart or not possible.
    """
    src = Path(src_path)
    dst = Path(dst_path)
    if not src.exists() or src.stat().st_size < 1024:
        return False

    with src.open('rb') as f:
        atoms = list(_iter_atoms(f))
        moov = next((a for a in atoms if a.typ == b'moov'), None)
        mdat = next((a for a in atoms if a.typ == b'mdat'), None)
        if moov is None or mdat is None:
            return False
        if moov.offset < mdat.offset:
            # already faststart
            return False

        f.seek(moov.offset, os.SEEK_SET)
        moov_bytes = f.read(moov.size)
        if len(moov_bytes) != moov.size:
            return False

        # Shift is moov size (we insert moov before mdat, after ftyp/free at front).
        # We patch offsets accordingly; this matches qtfaststart's behavior.
        patched_moov = _patch_chunk_offsets(moov_bytes, shift=moov.size)

        # Write output: everything except moov, but insert patched moov after the first atom (usually ftyp).
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open('wb') as out:
            inserted = False
            for atom in atoms:
                if atom.typ == b'moov':
                    continue
                f.seek(atom.offset, os.SEEK_SET)
                chunk = f.read(atom.size)
                out.write(chunk)
                if not inserted and atom.typ == b'ftyp':
                    out.write(patched_moov)
                    inserted = True
            if not inserted:
                # fallback: append moov at start if ftyp missing
                out.seek(0, os.SEEK_SET)
                original = out.read()
                out.seek(0, os.SEEK_SET)
                out.write(patched_moov)
                out.write(original)
    return True


def faststart_inplace(path: str | Path) -> bool:
    p = Path(path)
    tmp = p.with_suffix(p.suffix + '.faststart.tmp')
    changed = faststart_to_file(p, tmp)
    if not changed:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False
    tmp.replace(p)
    return True


def has_moov_atom(path: str | Path) -> bool:
    p = Path(path)
    if not p.exists() or p.stat().st_size < 32:
        return False
    try:
        with p.open('rb') as f:
            for atom in _iter_atoms(f):
                if atom.typ == b'moov':
                    return True
        return False
    except Exception:
        return False

