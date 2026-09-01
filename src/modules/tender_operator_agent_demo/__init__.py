"""Tender Operator Agent demo module."""

# The package uses compatibility facades around historical tender-demo code.
# Install source-bound decision-usefulness layers before those facades capture
# legacy callables, so R10.1 reports retain concrete material terms.
from src.modules.tender_operator_agent_demo.decision_useful_runtime_patch import (
    install as _install_decision_useful_runtime_patch,
)
from src.modules.tender_operator_agent_demo.decision_useful_output_patch import (
    install as _install_decision_useful_output_patch,
)
from src.modules.tender_operator_agent_demo.grounded_fallback_patch import (
    install as _install_grounded_fallback_patch,
)
from src.modules.tender_operator_agent_demo.grounded_fallback_followup import (
    install as _install_grounded_fallback_followup,
)

_install_decision_useful_runtime_patch()
_install_decision_useful_output_patch()
_install_grounded_fallback_patch()
_install_grounded_fallback_followup()
