class BudgetExhaustedError(Exception):
    """Raised when the actguard budget limit is exceeded during research."""

    def __init__(self, message: str = "Research budget exceeded."):
        super().__init__(message)
