"""Write named solids to a STEP file in millimetres, the same way every time."""
import re
from pathlib import Path

from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool

from .quiet import quiet
from .transform import settled

FIXED_TIME = "2000-01-01T00:00:00"    # a fixed header time, so the same solids give the same file
HEADER = re.compile(r"FILE_NAME\('[^']*','[^']*'")


def write_solids(path, named, title):
    """Write {name: solid} to path, each solid under its own name. title goes in the file header.

    Names must be plain ASCII text: the kernel damages other characters when it writes them.
    """
    quiet()
    document = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    table = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    for name, solid in named.items():
        TDataStd_Name.Set_s(table.AddShape(settled(solid), False), TCollection_ExtendedString(name))
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    writer = STEPCAFControl_Writer()
    if not writer.Transfer(document, STEPControl_AsIs) or writer.Write(str(path)) != IFSelect_RetDone:
        raise OSError(f"could not write the STEP file {path}")
    path = Path(path)
    plain = re.sub(r"[^A-Za-z0-9 ._-]", "", title)
    text = HEADER.sub(f"FILE_NAME('{plain}','{FIXED_TIME}'", path.read_text(encoding="utf-8"), count=1)
    path.write_text(text, encoding="utf-8", newline="\n")
