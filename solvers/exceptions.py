class SolverError(Exception):
    def __init__(self, message, stage=None, **diagnostics):
        super().__init__(message)
        self.stage = stage
        self.diagnostics = diagnostics


class ConfigurationError(SolverError):
    pass


class UnsupportedCaseError(SolverError):
    pass


class VersionMismatchError(ConfigurationError):
    pass


class PreprocessError(SolverError):
    pass


class MeshConversionError(PreprocessError):
    pass


class ExecutionError(SolverError):
    pass


class SolverCrashError(ExecutionError):
    pass


class SolverTimeoutError(ExecutionError):
    pass


class CancelledError(ExecutionError):
    pass


class PostprocessError(SolverError):
    pass


class MissingOutputError(PostprocessError):
    pass


class MonitorParseError(PostprocessError):
    pass


class FieldParseError(PostprocessError):
    pass


class UnsupportedResultFormatError(FieldParseError):
    pass
