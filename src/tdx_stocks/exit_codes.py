from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    UNKNOWN_ERROR = 1
    INPUT_MISSING = 2
    VERIFICATION_FAILED = 3
    BUILD_CHECK_FAILED = 4
    LOCKED = 5
    USAGE_ERROR = 6
    NO_DATA = 7
    INTERRUPTED = 130


class CliError(Exception):
    code = ExitCode.UNKNOWN_ERROR


class UsageError(CliError):
    code = ExitCode.USAGE_ERROR


class InputMissingError(CliError):
    code = ExitCode.INPUT_MISSING


class VerificationFailedError(CliError):
    code = ExitCode.VERIFICATION_FAILED


class BuildCheckFailedError(CliError):
    code = ExitCode.BUILD_CHECK_FAILED


class LockedError(CliError):
    code = ExitCode.LOCKED


class NoDataError(CliError):
    code = ExitCode.NO_DATA
