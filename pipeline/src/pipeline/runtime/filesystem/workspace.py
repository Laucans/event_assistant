"""A repository root, and the paths this package derives from it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pipeline.runtime.filesystem.paths import repo_root


@dataclass(frozen=True)
class Workspace:
    """The checkout a run works against."""

    root: Path

    @classmethod
    def here(cls) -> "Workspace":
        """The checkout this package lives in, resolved by `paths`."""
        return cls(repo_root())

    @property
    def loop_dir(self) -> Path:
        return self.root / ".llocal/agent-loop"

    @property
    def state(self) -> Path:
        return self.root / ".llocal/agent-loop/state"

    @property
    def ledger(self) -> Path:
        return self.root / ".llocal/agent-loop/costs.tsv"

    @property
    def flow_db(self) -> Path:
        return self.root / ".llocal/agent-loop/flow_states.db"

    @property
    def review_dir(self) -> Path:
        return self.root / ".llocal/pr-review"

    @property
    def review_ledger(self) -> Path:
        return self.root / ".llocal/pr-review/costs.tsv"

    @property
    def skills(self) -> Path:
        return self.root / ".claude/skills"

    @property
    def ci_workflow(self) -> Path:
        return self.root / ".github/workflows/ci.yml"

    def rel(self, path) -> str:
        """The path relative to this root when that is possible, else as is."""
        try:
            return str(Path(path).relative_to(self.root))
        except ValueError:
            return str(path)
