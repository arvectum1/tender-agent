"""Tender Operator Agent demo module."""

# The package uses compatibility facades around historical tender-demo code.
# Install the source-bound decision-usefulness layer before those facades
# capture legacy callables, so R10.1 reports retain concrete material terms.
from src.modules.tender_operator_agent_demo.decision_useful_runtime_patch import (
    install as _install_decision_useful_runtime_patch,
)

_install_decision_useful_runtime_patch()
