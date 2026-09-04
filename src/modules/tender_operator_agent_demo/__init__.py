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
from src.modules.tender_operator_agent_demo.grounded_fallback_evidence_binding import (
    install as _install_grounded_fallback_evidence_binding,
)
from src.modules.tender_operator_agent_demo.grounded_fallback_runtime_contract import (
    install as _install_grounded_fallback_runtime_contract,
)
from src.modules.tender_operator_agent_demo.d07_scope_output_binding import (
    install as _install_d07_scope_output_binding,
)

_install_decision_useful_runtime_patch()
_install_decision_useful_output_patch()
_install_grounded_fallback_patch()
_install_grounded_fallback_followup()
_install_grounded_fallback_evidence_binding()
_install_grounded_fallback_runtime_contract()
# Must be installed last: D07 semantic scope is authoritative at serialization.
_install_d07_scope_output_binding()
