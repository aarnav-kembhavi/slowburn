"""Shared parallel task runner for all experiments.

* a process pool of at most ``MAX_WORKERS`` workers, each pinned to ONE thread (LightGBM/OpenMP
  otherwise starts a full thread pool per process; measured ~1.35 GB vs ~0.34 GB per worker);
* every finished task is persisted to ``cache_dir`` immediately, so a re-run resumes;
* if a worker dies (``BrokenProcessPool``), a fresh pool continues with the remaining tasks.

Tasks and results must be picklable; ``func`` and ``init`` must be importable top-level
functions (Windows uses the spawn start method).
"""

from __future__ import annotations

import hashlib
import lzma
import os
import pickle
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any

MAX_WORKERS = 6


def _pinned_init(init: Callable | None, init_args: tuple) -> None:
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    if init is not None:
        init(*init_args)


def stable_id(obj: Any) -> str:
    """Short stable hash of a task's identity (its repr)."""
    return hashlib.blake2b(repr(obj).encode(), digest_size=10).hexdigest()


def run_tasks(
    func: Callable[[Any], Any],
    tasks: Sequence[Any],
    *,
    workers: int = 1,
    init: Callable | None = None,
    init_args: tuple = (),
    cache_dir: str | Path | None = None,
    task_key: Callable[[Any], Any] = lambda t: t,
    log: Callable[..., None] = print,
    max_pool_restarts: int = 3,
    progress_every: int = 20,
) -> list[Any]:
    """Run ``func`` over ``tasks``; return results in task order."""
    workers = max(1, min(int(workers), MAX_WORKERS, os.cpu_count() or 1))
    cache = Path(cache_dir) if cache_dir is not None else None
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)

    def path_of(i: int) -> Path | None:
        return cache / f"{stable_id(task_key(tasks[i]))}.pkl" if cache is not None else None

    done: dict[int, Any] = {}
    for i in range(len(tasks)):
        p = path_of(i)
        if p is not None and p.exists():
            with p.open("rb") as fh:
                done[i] = pickle.load(fh)
        elif p is not None and p.with_suffix(".pkl.xz").exists():  # compressed in place (lossless)
            with lzma.open(p.with_suffix(".pkl.xz"), "rb") as fh:
                done[i] = pickle.load(fh)
    if done:
        log(f"  resuming: {len(done)}/{len(tasks)} tasks already done")

    def keep(i: int, res: Any) -> None:
        done[i] = res
        p = path_of(i)
        if p is not None:
            tmp = p.with_suffix(".tmp")
            with tmp.open("wb") as fh:
                pickle.dump(res, fh)
            tmp.replace(p)
        if len(done) % progress_every == 0 or len(done) == len(tasks):
            log(f"  tasks {len(done)}/{len(tasks)} done")

    if workers == 1:
        _pinned_init(init, init_args)
        for i in range(len(tasks)):
            if i not in done:
                keep(i, func(tasks[i]))
        return [done[i] for i in range(len(tasks))]

    for attempt in range(max_pool_restarts + 1):
        pending = [i for i in range(len(tasks)) if i not in done]
        if not pending:
            break
        try:
            with ProcessPoolExecutor(workers, initializer=_pinned_init,
                                     initargs=(init, init_args)) as ex:  # fmt: skip
                futures = {ex.submit(func, tasks[i]): i for i in pending}
                for fut in as_completed(futures):
                    keep(futures[fut], fut.result())
        except BrokenProcessPool:
            log(f"  worker died (pool attempt {attempt + 1}); "
                f"{len(tasks) - len(done)} tasks left")  # fmt: skip
    missing = len(tasks) - len(done)
    if missing:
        raise RuntimeError(f"{missing} tasks failed after {max_pool_restarts} pool restarts")
    return [done[i] for i in range(len(tasks))]
