"""Perturb a tracked file, run something, restore it — roadmap H23.

One implementation, several callers: the gates that prove a mechanism fires by
breaking a file on purpose (`A13.sh`, `H21.sh`, and any red-first probe). Each
had its own copy of the same read-write-restore dance, which is the drift `H9`
exists to stop — and the second copy also hid a hazard neither author saw.

**Why this module exists at all.** CPython decides whether a cached ``.pyc``
is usable by comparing it against the source's *(whole-second mtime, byte
size)* pair. Rewrite a ``.py`` within the same second at the same size and
that pair does not move, so the old bytecode keeps being imported. Both
directions of that are wrong, and the worse one is the quiet one:

- the **restoration** can be masked, and the repository then behaves as if the
  perturbation were still in place. Measured live: `A10b`'s probe changed the
  G:U weight in ``seed_aligner.py`` from 0.5 to 0.6 and restored it with the
  bytes asserted identical, after which the full suite failed
  ``test_gu_wobble_detection`` with ``19.6 != 19.5`` while the file on disk
  said ``0.5``;
- the **perturbation** can be masked, and then the gate's own measurement is
  vacuous: it writes the broken version, the import reads the old bytecode,
  the test stays green, and the gate reports "the mechanism fires" having
  fired nothing. A gate that cannot fail is the thing invariant 5 is for.

So every write here is followed by dropping the bytecode for that source.
Dropping it *after* the write (rather than before) is deliberate: a process
that compiles the file between our two steps writes a cache we then remove,
and anything compiling afterwards compiles the bytes we left behind.

``tests/hooks/test_perturb.py`` keeps a control that reproduces the stale read
deterministically. If CPython ever changes the rule, that control goes red and
says so, rather than this module quietly becoming ceremony.
"""

from __future__ import annotations

import contextlib
import importlib.util
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

__all__ = ["invalidate_bytecode", "patched", "perturbed", "write_bytes"]


def invalidate_bytecode(path: str | Path) -> list[Path]:
    """Remove every cached bytecode file belonging to ``path``.

    Args:
        path: Source file. Anything that is not ``.py`` is a no-op.

    Returns:
        The cache files actually removed, for callers that want to assert the
        invalidation happened rather than assume it.
    """
    source = Path(path)
    if source.suffix != ".py":
        return []

    candidates: set[Path] = set()
    with contextlib.suppress(ValueError, NotImplementedError):
        # Honours `sys.pycache_prefix`, which a plain `__pycache__` glob misses.
        candidates.add(Path(importlib.util.cache_from_source(str(source))))
    cache_dir = source.parent / "__pycache__"
    if cache_dir.is_dir():
        # Other interpreters' tags live here too and are just as stale.
        candidates.update(cache_dir.glob(f"{source.stem}.*.pyc"))
    candidates.add(source.with_suffix(".pyc"))  # pre-PEP-3147 layout

    removed: list[Path] = []
    for candidate in sorted(candidates):
        try:
            if candidate.is_file():
                candidate.unlink()
                removed.append(candidate)
        except OSError:
            # A cache we cannot remove is worth reporting, not worth crashing
            # a gate over; the caller's own assertions will catch the effect.
            continue
    return removed


def write_bytes(path: str | Path, data: bytes) -> None:
    """Write ``data`` to ``path`` and make sure the next import sees it.

    Args:
        path: File to write.
        data: Exact bytes to write.
    """
    target = Path(path)
    target.write_bytes(data)
    invalidate_bytecode(target)


@contextmanager
def perturbed(
    path: str | Path,
    old: str,
    new: str,
    *,
    count: int = 1,
    encoding: str = "utf-8",
) -> Iterator[Path]:
    """Replace ``old`` with ``new`` inside ``path``, then restore it exactly.

    Args:
        path: File to perturb.
        old: Anchor text, which must occur exactly ``count`` times.
        new: Replacement text.
        count: How many occurrences of ``old`` are required.
        encoding: Text encoding of the file.

    Yields:
        The perturbed path, for convenience.

    Raises:
        ValueError: If ``old`` does not occur exactly ``count`` times — an
            anchor that matches twice silently perturbs the wrong thing, and
            one that matches nothing makes the measurement vacuous.
        RuntimeError: If the original bytes could not be put back.
    """
    target = Path(path)
    original = target.read_bytes()
    text = original.decode(encoding)
    found = text.count(old)
    if found != count:
        raise ValueError(
            f"{target}: anchor occurs {found} times, expected {count} — "
            "refusing to perturb"
        )
    try:
        write_bytes(target, text.replace(old, new, count).encode(encoding))
        yield target
    finally:
        _restore(target, original)


@contextmanager
def patched(
    path: str | Path, text: str, *, encoding: str = "utf-8"
) -> Iterator[Path]:
    """Replace the whole contents of ``path``, then restore it exactly.

    `H21.sh` needs this shape: it builds a modified workflow in full rather
    than anchoring on a substring.

    Args:
        path: File to replace.
        text: New whole contents.
        encoding: Text encoding to write with.

    Yields:
        The patched path.

    Raises:
        RuntimeError: If the original bytes could not be put back.
    """
    target = Path(path)
    original = target.read_bytes()
    try:
        write_bytes(target, text.encode(encoding))
        yield target
    finally:
        _restore(target, original)


def _restore(target: Path, original: bytes) -> None:
    """Put ``original`` back and prove it, or raise.

    A gate must not measure by corrupting the repository, so the restoration
    is asserted here rather than left to each caller to remember.

    Args:
        target: File to restore.
        original: Bytes it had before.

    Raises:
        RuntimeError: If the bytes on disk still differ afterwards.
    """
    write_bytes(target, original)
    if target.read_bytes() != original:
        raise RuntimeError(
            f"{target}: could not be restored — the working tree is dirty and "
            "any later measurement is meaningless"
        )
