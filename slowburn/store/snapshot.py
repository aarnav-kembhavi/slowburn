"""Deduplicated daily snapshot store.

A snapshot is a per-file manifest (file id -> ordered chunk hashes). Chunk bytes are stored once
in a content-addressed pool and reference-counted across retained snapshots, so deleting a
snapshot frees exactly the chunks no other retained snapshot uses.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field


def chunk_hash(buf: bytes) -> str:
    return hashlib.blake2b(buf, digest_size=16).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    id: int
    day: int
    manifest: dict[str, tuple[str, ...]]

    @property
    def chunk_set(self) -> frozenset[str]:
        return frozenset(h for hs in self.manifest.values() for h in hs)


@dataclass
class SnapshotStore:
    snapshots: dict[int, Snapshot] = field(default_factory=dict)
    _pool: dict[str, bytes] = field(default_factory=dict)
    _refs: Counter = field(default_factory=Counter)

    def add(self, day: int, files: dict[str, list[bytes]]) -> Snapshot:
        """Take a snapshot of ``files`` (file id -> chunk list) at the end of ``day``."""
        sid = max(self.snapshots, default=-1) + 1
        manifest = {}
        for fid, chunks in files.items():
            hs = []
            for c in chunks:
                h = chunk_hash(c)
                self._pool.setdefault(h, c)
                hs.append(h)
            manifest[fid] = tuple(hs)
        snap = Snapshot(sid, day, manifest)
        self.snapshots[sid] = snap
        self._refs.update(snap.chunk_set)
        return snap

    def delete(self, sid: int) -> None:
        snap = self.snapshots.pop(sid)
        self._refs.subtract(snap.chunk_set)
        for h in snap.chunk_set:
            if self._refs[h] <= 0:
                del self._refs[h]
                del self._pool[h]

    def retain_only(self, keep: set[int]) -> None:
        for sid in [s for s in self.snapshots if s not in keep]:
            self.delete(sid)

    def ids(self) -> list[int]:
        return sorted(self.snapshots)

    def days(self) -> list[int]:
        return sorted(s.day for s in self.snapshots.values())

    def by_day(self, day: int) -> Snapshot | None:
        return next((s for s in self.snapshots.values() if s.day == day), None)

    def chunk(self, h: str) -> bytes:
        return self._pool[h]

    def file_bytes(self, sid: int, fid: str) -> bytes:
        return b"".join(self._pool[h] for h in self.snapshots[sid].manifest[fid])

    @property
    def unique_chunks(self) -> int:
        return len(self._pool)

    @property
    def unique_bytes(self) -> int:
        return sum(len(b) for b in self._pool.values())
