"""Le registre des consignes : un stage n'en a que s'il est nomme ici."""

from pipeline.domain.prompts.definitions.agentic_dev_loop.business_analyst \
    import BUSINESS_ANALYST
from pipeline.domain.prompts.definitions.agentic_dev_loop.code import CODE
from pipeline.domain.prompts.definitions.agentic_dev_loop.planner \
    import PLANNER

# The instructions specific to each stage. `{num}`, `{title}` and
# `{milestone}` are substituted with the task in flight.
EXTRA = {
    "business-analyst": BUSINESS_ANALYST,
    "code": CODE,
    "planner": PLANNER,
}

NO_INSTRUCTIONS: frozenset[str] = frozenset({"create-test"})
