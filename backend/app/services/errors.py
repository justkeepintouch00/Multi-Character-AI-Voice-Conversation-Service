class ServiceError(RuntimeError):
    pass


class ResourceNotFoundError(ServiceError):
    pass


class ResourceConflictError(ServiceError):
    pass


class InvalidResourceInputError(ServiceError):
    pass
