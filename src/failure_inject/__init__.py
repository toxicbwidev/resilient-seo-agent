"""Failure injection harness for the resilient agent demos.

Usage in a demo script:

    from src.failure_inject import FailureInjector, scenarios

    real_client_call = openai_client.chat.completions.create
    injector = scenarios.scenario_1_rate_limit()
    injected_call = injector.wrap(real_client_call)

    # ...use injected_call instead of real_client_call in the pipeline...

    print(injector.injections_fired)  # log of what we triggered
"""
from . import exceptions, scenarios
from .exceptions import (
    InjectedCorrupted,
    InjectedFailure,
    InjectedOutage,
    InjectedRateLimit,
    InjectedTimeout,
    InjectedToolFailure,
)
from .injector import FailureInjector

__all__ = [
    "FailureInjector",
    "InjectedFailure",
    "InjectedRateLimit",
    "InjectedOutage",
    "InjectedTimeout",
    "InjectedToolFailure",
    "InjectedCorrupted",
    "scenarios",
    "exceptions",
]
