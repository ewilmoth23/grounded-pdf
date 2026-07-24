class GroundedPdfError(Exception):
    def __init__(self, message: str, *, code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class FileValidationError(GroundedPdfError):
    def __init__(self, message: str, code: str = "invalid_pdf") -> None:
        super().__init__(message, code=code, status_code=422)


class ProviderUnavailableError(GroundedPdfError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="provider_unavailable", status_code=503)


class VectorStoreError(GroundedPdfError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="vector_store_error", status_code=503)
