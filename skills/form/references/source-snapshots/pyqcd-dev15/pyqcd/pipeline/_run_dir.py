"""Collision-resistant run-directory allocation shared by serial and MPI."""

from __future__ import annotations

import os
import secrets
import time


_MAX_RESERVATION_ATTEMPTS = 16


def _validate_tag(tag: str | None) -> str | None:
    """Reject path-like display tags before any directory is created."""
    if tag is None or tag == '':
        return tag
    if not isinstance(tag, str):
        raise ValueError(f'tag must be a string or None, got {tag!r}')
    if ('\x00' in tag or os.path.basename(tag) != tag
            or (os.path.altsep is not None and os.path.altsep in tag)):
        raise ValueError(f'tag must be a single path component, got {tag!r}')
    return tag


def reserve_unique_run_dir(output_root: str, tag: str | None = None) -> str:
    """Atomically reserve and return a unique default run directory.

    The human-readable second remains in the name, while nanoseconds, PID,
    and a 64-bit random token prevent independent jobs from selecting the
    same candidate.  ``exist_ok=False`` is the final race-free arbiter.
    """
    tag = _validate_tag(tag)
    os.makedirs(output_root, exist_ok=True)
    for _ in range(_MAX_RESERVATION_ATTEMPTS):
        now_ns = time.time_ns()
        stamp = time.strftime(
            '%Y%m%d_%H%M%S', time.localtime(now_ns // 1_000_000_000))
        subsecond = now_ns % 1_000_000_000
        name = (
            f'output_{stamp}_{subsecond:09d}_p{os.getpid()}_'
            f'{secrets.token_hex(8)}'
        )
        if tag:
            name = f'{name}_{tag}'
        run_dir = os.path.join(output_root, name)
        try:
            os.makedirs(run_dir, exist_ok=False)
        except FileExistsError:
            continue
        return run_dir

    raise FileExistsError(
        f'failed to reserve a unique run directory under {output_root!r} '
        f'after {_MAX_RESERVATION_ATTEMPTS} attempts')
