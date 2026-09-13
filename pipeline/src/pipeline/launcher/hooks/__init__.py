"""The hooks, as importable and testable code.

They run under the system python, outside the venv, and have to return in
milliseconds: **standard library only**, and above all no agent SDK
import. The entry points in `scripts/hooks/` do nothing but add
`pipeline/src` to the path and call `main()`.

Every hook fails open: a broken hook must never be what stops the work.
"""
