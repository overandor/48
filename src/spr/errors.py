"""Domain errors for the production SPR package."""

from __future__ import annotations


class SPRError(Exception):
    """Base error for all Semantic Protocol Runtime failures."""

    code = "SPR_ERROR"

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        if self.hint:
            return f"{self.code}: {self.message}\nHint: {self.hint}"
        return f"{self.code}: {self.message}"


class SPRParseError(SPRError):
    code = "SPR_PARSE_ERROR"


class SPRPolicyError(SPRError):
    code = "SPR_POLICY_DENIED"


class SPRPlanningError(SPRError):
    code = "SPR_PLANNING_FAILED"


class SPRLoweringError(SPRError):
    code = "SPR_LOWERING_FAILED"


class SPRRuntimeError(SPRError):
    code = "SPR_RUNTIME_FAILED"


class SPRAuditError(SPRError):
    code = "SPR_AUDIT_FAILED"
