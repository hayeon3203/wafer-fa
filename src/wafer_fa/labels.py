CLASSES = [
    "Center", "Donut", "Edge-Loc", "Edge-Ring", "Loc",
    "Random", "Scratch", "Near-full", "none",
]
LABEL_TO_IDX = {name: i for i, name in enumerate(CLASSES)}
IDX_TO_LABEL = {i: name for i, name in enumerate(CLASSES)}
