class OrdercastApiValidationException(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class OrdercastApiServerException(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
