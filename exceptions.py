class Error(Exception):
    """Base class for exceptions in this module."""
    pass


class MissingParameterError(Error):
    code = 1001
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        repr(self.msg)


class InvalidParameterError(Error):
    code = 1001
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        repr(self.msg)


class InternalServerError(Error):
    code = 1002
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        repr(self.msg)


