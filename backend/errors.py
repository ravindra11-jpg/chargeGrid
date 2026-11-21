class ApiError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra

    def to_dict(self):
        return {"error": self.message, **self.extra}
