"""The measure layer: numbers about a built design. It reports; it never judges.

    clearance     gaps between solids along a motion (with a proof that nothing was missed) and at a pose
    approach      does a pair come together, is a seat bearing, is a moved set withdrawn
    attachment    what touches what at a pose, what is not connected to the base, measured mounts, floating fixtures
    mass          mass and centre of mass per group and for the whole robot
    compression   how deep a solid presses into a ball or ring
    run           sharing clearance work between worker processes
    summary       all of the above for one design source, as one record

Supporting modules: scene (solids set up for measuring), pairs (broad phase), search (the adaptive proof),
proofs (exact shortcuts for straight slides), sets (connected sets).
"""
