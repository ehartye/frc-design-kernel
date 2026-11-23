"""A solid as triangles, for drawing it or handing it to a physics engine. The solid itself is not altered."""
from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_REVERSED
from OCP.TopLoc import TopLoc_Location

from .between import faces


def triangles(shape, deflection_mm=0.5, angle_rad=0.3):
    """{"vertices": [[x, y, z], ...], "triangles": [[i, j, k], ...]} for a shape, in millimetres.

    No triangle strays more than deflection_mm from the true surface. Triangles are wound so their normals point out
    of the solid. Vertices are not shared between faces.
    """
    copy = BRepBuilderAPI_Copy(shape, True, False).Shape()      # meshing would otherwise leave triangles on the caller's shape
    BRepMesh_IncrementalMesh(copy, deflection_mm, False, angle_rad)
    vertices, found = [], []
    for face in faces(copy):
        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face, location)
        if mesh is None:
            continue
        start, move = len(vertices), location.Transformation()
        vertices += [list(mesh.Node(i).Transformed(move).Coord()) for i in range(1, mesh.NbNodes() + 1)]
        flip = face.Orientation() == TopAbs_REVERSED
        for i in range(1, mesh.NbTriangles() + 1):
            a, b, c = (n - 1 + start for n in mesh.Triangle(i).Get())
            found.append([a, c, b] if flip else [a, b, c])
    return {"vertices": vertices, "triangles": found}
