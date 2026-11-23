"""Custom shape "tine": a fork tine with a curved underside.

Drawn at the origin: the root face is at x = 0, the tine runs along +X, its flat top is at z = 0 and it spans
y = 0 to widthMm. The design source places it with "place".
"""
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GC import GC_MakeArcOfCircle
from OCP.gp import gp_Pnt, gp_Vec


def build(parameters):
    length, width = parameters["lengthMm"], parameters["widthMm"]
    root, tip = parameters["rootMm"], parameters["tipMm"]
    top_root, top_tip = gp_Pnt(0, 0, 0), gp_Pnt(length, 0, 0)
    under_tip, under_root = gp_Pnt(length, 0, -tip), gp_Pnt(0, 0, -root)
    belly = gp_Pnt(length / 2, 0, -(root + tip) / 2 + (root - tip) / 4)
    wire = BRepBuilderAPI_MakeWire()
    for start, end in ((top_root, top_tip), (top_tip, under_tip)):
        wire.Add(BRepBuilderAPI_MakeEdge(start, end).Edge())
    wire.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(under_tip, belly, under_root).Value()).Edge())
    wire.Add(BRepBuilderAPI_MakeEdge(under_root, top_root).Edge())
    face = BRepBuilderAPI_MakeFace(wire.Wire(), True).Face()
    return BRepPrimAPI_MakePrism(face, gp_Vec(0, width, 0)).Shape()
