"""Stop the CAD kernel printing its own progress notes, so the library's one-line messages stay readable."""
from OCP.Message import Message

_done = False


def quiet():
    """Remove the kernel's console printers for this process. Safe to call many times."""
    global _done
    if not _done:
        Message.DefaultMessenger_s().ChangePrinters().Clear()
        _done = True
