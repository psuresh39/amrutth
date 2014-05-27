class FoodTruckError(Exception):
    """Base class for exceptions in this module."""
    pass


class MissingParameterError(FoodTruckError):
    code = 1001
    http_code = 400
    def __init__(self, msg="parameter is missing in query"):
        self.msg = msg
    def __str__(self):
        return repr(self.msg)


class InvalidParameterError(FoodTruckError):
    code = 1002
    http_code = 400
    def __init__(self, msg="parameter is invalid"):
        self.msg = msg
    def __str__(self):
        return repr(self.msg)


class InternalServerError(FoodTruckError):
    code = 1003
    http_code = 500
    def __init__(self, msg="internal server error"):
        self.msg = msg
    def __str__(self):
        return repr(self.msg)


