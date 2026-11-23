"""Read a STEP file into named solids, each at its installed place."""
from collections import Counter

from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool

from .props import solids
from .quiet import quiet

try:
    from OCP.TDF import TDF_LabelSequence
except ImportError:    # newer kernels moved the label list
    from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence


def repaired(name):
    """Undo the usual damage to a name with accented letters or symbols (UTF-8 text read one byte at a time)."""
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def label_name(label):
    attribute = TDataStd_Name()
    return repaired(attribute.Get().ToExtString()) if label.FindAttribute(TDataStd_Name.GetID_s(), attribute) else ""


def read_solids(path):
    """{name: solid} for every solid in the STEP file at path.

    A solid takes the name of the part that holds it. When a name is missing or used more than once, each such solid
    is named "name [occurrence]" by its position in the file's assembly tree, so every name is unique.
    """
    quiet()
    document = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    table = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    reader = STEPCAFControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone or not reader.Transfer(document):
        raise ValueError(f"could not read the STEP file {path}")
    bodies = []

    def visit(label, location, indices):
        children = TDF_LabelSequence()
        table.GetComponents_s(label, children)
        if children.Length():
            for i in range(1, children.Length() + 1):
                child, definition = children.Value(i), TDF_Label()
                if not table.GetReferredShape_s(child, definition):
                    raise ValueError(f"the STEP file {path} has an occurrence with no definition")
                visit(definition, location.Multiplied(table.GetLocation_s(child)), indices + [i])
            return
        for n, solid in enumerate(solids(table.GetShape_s(label).Moved(location)), 1):
            bodies.append((label_name(label), ".".join(map(str, indices + [n])), solid))

    roots = TDF_LabelSequence()
    table.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        visit(roots.Value(i), TopLoc_Location(), [i])
    counts = Counter(name for name, _, _ in bodies)
    return {name if name and counts[name] == 1 else f"{name or 'Solid'} [{occurrence}]": solid for name, occurrence, solid in bodies}
