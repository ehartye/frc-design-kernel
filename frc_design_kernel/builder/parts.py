"""Solids taken from supplier or field STEP files by name. A part is placed, never changed."""
import difflib
import hashlib

from ..errors import DesignError
from ..kernel.step_read import read_solids


class Parts:
    """The STEP files one design draws on: reads each file once and reports what was taken from it."""

    def __init__(self, folder):
        self.folder = folder
        self.files = {}     # {relative file: {solid name: solid}}
        self.taken = {}     # {relative file: [(solid name in the file, name in the design)]}

    def take(self, part, name, where):
        """The solid part["solid"] from the file part["file"], for the design solid called name."""
        file = part["file"]
        if file not in self.files:
            try:
                self.files[file] = read_solids(self.folder / file)
            except ValueError as problem:
                raise DesignError(where, str(problem), "Check that the file is a STEP file with solid bodies") from None
        found = self.files[file]
        if part["solid"] not in found:
            close = difflib.get_close_matches(part["solid"], found, 3)
            hint = f"Did you mean {' or '.join(repr(c) for c in close)}? " if close else ""
            raise DesignError(where, f'the file "{file}" has no solid named "{part["solid"]}"', f"{hint}It has {len(found)} solids: {', '.join(sorted(found)[:12])}")
        self.taken.setdefault(file, []).append((part["solid"], name))
        return found[part["solid"]]

    def report(self):
        """One manifest row per file used, with its fingerprint and the solids taken from it."""
        return [{"file": file, "sha256": hashlib.sha256((self.folder / file).read_bytes()).hexdigest(),
                 "solids": [{"solid": solid, "as": name} for solid, name in sorted(self.taken[file])]} for file in sorted(self.taken)]
