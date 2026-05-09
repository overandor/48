"""Console entrypoint wrappers for the prototype scripts.

These wrappers make the repository installable before the larger modular split.
They execute the existing top-level scripts as if they were run with
`python <script>.py`, preserving current CLI behavior while enabling
`pip install -e .` and console commands from `pyproject.toml`.
"""

from __future__ import annotations

import runpy


def spr() -> None:
    runpy.run_module("semantic_protocol_runtime", run_name="__main__")


def spr_voice() -> None:
    runpy.run_module("semantic_protocol_voice", run_name="__main__")


def spr_terminal_agent() -> None:
    runpy.run_module("voice_terminal_agent", run_name="__main__")


def spr_complete() -> None:
    runpy.run_module("completefication", run_name="__main__")


def spr_ui() -> None:
    runpy.run_module("completefication_neomorphic_ui", run_name="__main__")
