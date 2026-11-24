"""Solids taken from supplier or field STEP files by name. A part is placed, never changed."""
import difflib
import hashlib

from ..errors import DesignError
from ..kernel.step_read import read_solids


class Parts:
    """The STEP files one design draws on: reads each file once and reports what was taken from it."""

    def __init__(self, design):
        self.design = design
        self.files = {}     # {(file or field, its name): {solid name: solid}}
        self.taken = {}     # {(file or field, its name): [(solid name in the file, name in the design)]}

    def take(self, part, name, where):
        """The solid part["solid"] from the part's file, for the design solid called name."""
        kind = "field" if "field" in part else "file"
        key = (kind, part[kind])
        if key not in self.files:
            try:
                self.files[key] = read_solids(self.design.part_file(part))
            except ValueError as problem:
                raise DesignError(where, str(problem), "Check that the file is a STEP file with solid bodies") from None
        found = self.files[key]
        if part["solid"] not in found:
            close = difflib.get_close_matches(part["solid"], found, 3)
            hint = f"Did you mean {' or '.join(repr(c) for c in close)}? " if close else ""
            raise DesignError(where, f'the file "{part[kind]}" has no solid named "{part["solid"]}"', f"{hint}It has {len(found)} solids: {', '.join(sorted(found)[:12])}")
        self.taken.setdefault(key, []).append((part["solid"], name))
        return found[part["solid"]]

    def report(self):
        """One manifest row per file used, with its fingerprint and the solids taken from it."""
        return [{kind: name, "sha256": hashlib.sha256(self.design.part_file({kind: name}).read_bytes()).hexdigest(),
                 "solids": [{"solid": solid, "as": built} for solid, built in sorted(self.taken[kind, name])]} for kind, name in sorted(self.taken)]
