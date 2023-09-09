class OrdercastApiValidationException(Exception):
    def __init__(self, message):
        super().__init__(message)


class OrdercastApiServerException(Exception):
    def __init__(self, message):
        super().__init__(message)
