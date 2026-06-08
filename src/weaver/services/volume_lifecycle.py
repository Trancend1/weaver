"""Derived volume lifecycle status (Sprint H2).

Status comes from data we already have: segment counts in the volume tree
plus the in-memory :class:`weaver.api.jobs.JobRegistry`. **No schema change**,
**no persistent column** — recomputed on every read so it is always honest.

The state machine is intentionally small:

```text
empty       — volume has zero segments
imported    — segments exist, none translated yet (done_count == 0)
in_progress — some segments done, some still pending
translated  — every segment is `translated` or `manual`
translating — any chapter in the volume has a running translate or batch job
              (overlays the static state above)
```

States deferred to later sprints (require state we do not yet persist):

- ``failed``    — needs persistent job state (Sprint I, ADR ``010``).
- ``exported``  — needs export tracking (Sprint K).
- ``qa_warning`` — would force a per-tree QA scan and violate Phase D Gate B1
  (the project tree must not run QA on render).

The lookup is O(volumes); per-volume it consults the JobRegistry once via the
project name + a precomputed chapter-id set, so the tree page stays fast.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from weaver.api.jobs import JobRegistry

VolumeStatus = Literal["empty", "imported", "in_progress", "translated", "translating"]


@dataclass(frozen=True)
class VolumeStatusView:
    """Derived status for one volume, plus a stable label for UI badges."""

    status: VolumeStatus
    label: str

    @property
    def is_terminal(self) -> bool:
        return self.status in {"empty", "imported", "translated"}


_LABELS: dict[VolumeStatus, str] = {
    "empty": "empty",
    "imported": "imported",
    "in_progress": "in progress",
    "translated": "translated",
    "translating": "translating",
}


def derive_volume_status(
    *,
    segment_count: int,
    done_count: int,
    chapter_ids: Iterable[str],
    project_name: str,
    jobs: JobRegistry | None,
) -> VolumeStatusView:
    """Compute the volume's status from its counts and the live JobRegistry.

    Args:
        segment_count: Total segments inside the volume across all chapters.
        done_count: Segments with status ``translated`` or ``manual``.
        chapter_ids: Chapter ids that belong to this volume.
        project_name: Owning project name (used to scope the JobRegistry lookup).
        jobs: Optional in-memory :class:`JobRegistry`. ``None`` skips the
            translating overlay (useful for pure-derivation tests).

    Returns:
        A :class:`VolumeStatusView` whose ``status`` matches the contract above.
        Never returns ``None``; an empty volume is ``empty``.
    """
    static_status: VolumeStatus
    if segment_count == 0:
        static_status = "empty"
    elif done_count == 0:
        static_status = "imported"
    elif done_count >= segment_count:
        static_status = "translated"
    else:
        static_status = "in_progress"

    if jobs is not None and _has_running_job(jobs, project_name, chapter_ids):
        return VolumeStatusView(status="translating", label=_LABELS["translating"])

    return VolumeStatusView(status=static_status, label=_LABELS[static_status])


def _has_running_job(jobs: JobRegistry, project_name: str, chapter_ids: Iterable[str]) -> bool:
    """Return True when any chapter inside the volume has a running translate job."""
    for chapter_id in chapter_ids:
        if jobs.find_running(project_name=project_name, chapter_id=chapter_id) is not None:
            return True
    return False
