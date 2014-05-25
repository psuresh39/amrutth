class Error(Exception):
    """Base class for exceptions in this module."""
    pass


class MissingParameterError(Error):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        repr(self.msg)


class InvalidParameterError(Error):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        repr(self.msg)


class InternalServerError(Error):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        repr(self.msg)


