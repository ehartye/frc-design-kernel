"""The one error type the library raises for a problem in a design source."""


class DesignError(ValueError):
    """A problem in a design source: where it is, what is wrong and how to fix it."""

    def __init__(self, where, problem, fix=""):
        self.where, self.problem, self.fix = where, problem, fix
        text = f"{where}: {problem}" if where else problem
        super().__init__(f"{text}. Fix: {fix}" if fix else text)

    def __reduce__(self):
        """So the error survives the trip back from a worker process."""
        return (DesignError, (self.where, self.problem, self.fix))

    def under(self, prefix):
        """The same error, with its place nested under a parent entry."""
        where = f"{prefix} {self.where}".strip() if self.where else prefix
        return DesignError(where, self.problem, self.fix)
