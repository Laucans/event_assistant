"""The instructions specific to the `planner` stage."""

PLANNER = """Every `pipeline:agent` issue of milestone #{milestone} is closed. Take the
open `pipeline:roadmap` issue with the lowest number — do not ask which one.
Open one `pipeline:milestone` issue for it, as a sub-issue of that roadmap
issue, and one `pipeline:agent` sub-issue per task slice, each blocked_by the
one before it. Then close milestone #{milestone}, and close the roadmap issue
it hangs off if that item is now fully delivered: the loop works on the
LOWEST-numbered open milestone, so leaving the finished one open makes every
later round roll over again instead of picking up what you just planned. Do
not add `pipeline:ready` to anything: the human opens the tap. Step 3 of the
skill applies in full: verify the ground truth in the repo, and if a
dependency the item builds on is not actually there, AGENT_LOOP_STOP with
what is missing rather than planning on top of it."""
