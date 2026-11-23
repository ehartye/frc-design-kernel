"""The try layer: physics trials described as data, run with the same method every time. See DESIGN.md section 13.

    campaign    plan the runs, count the cost, run them, gather the record
    scene       a trial definition and named solids turned into a runnable scene
    planar      the fixed-step solver for one round piece in a plane
    contact     piece against segment or arc; stick and smooth friction
    drives      belts, rollers and wheels: imposed or motor-driven
    rules       conditions and events as data
    record      criterion, control, brackets, step comparison, result word
    fit         a trace reduced to one path operation
    custom      custom force laws and criteria through the narrow door
"""
