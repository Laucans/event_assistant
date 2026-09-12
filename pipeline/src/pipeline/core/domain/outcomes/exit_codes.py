"""What the process exits with.

Documented in `--help` and in the README: an outer scheduler reads these, and
a number that moved silently would make it retry the wrong things.

Ils vivent seuls, sans rien importer, parce que tout le monde les lit : le
`Result` qui les porte, les points d'entree qui les rendent, et les tests qui
les asserent.
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_HALT = 1        # stopped on purpose — a human has to look
EXIT_STAGE_FAILED = 2  # a stage did not produce a usable result
EXIT_QUOTA = 3       # subscription window exhausted — retry later, unchanged
EXIT_CRASH = 4       # anything unexpected: the traceback is in run.log
EXIT_INTERRUPTED = 130
