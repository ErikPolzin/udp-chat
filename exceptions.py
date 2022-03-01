class ItemNotFoundException(Exception):
    """Raised when requesting an invalid item."""


class ItemAlreadyExistsException(Exception):
    """Raised when adding al anready existing item."""