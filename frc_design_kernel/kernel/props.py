"""What can be measured on one shape: its solids, validity, volume and bounding box."""
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer


def solids(shape):
    """Every solid body inside a shape."""
    found, explorer = [], TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        found.append(explorer.Current())
        explorer.Next()
    return found


def is_valid(shape):
    return BRepCheck_Analyzer(shape).IsValid()


def volume(shape):
    """Volume in cubic millimetres."""
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, properties, True)
    return properties.Mass()


def bounds(shape):
    """The bounding box [xmin, ymin, zmin, xmax, ymax, zmax] in millimetres, fitted to the true surfaces."""
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    return [*box.CornerMin().Coord(), *box.CornerMax().Coord()]


def centre(shape):
    """The centre of the shape's volume [x, y, z] in millimetres: its centre of mass if it is the same stuff throughout."""
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, properties, True)
    return list(properties.CentreOfMass().Coord())
