from daol_fascope import cases


def test_search_cases_returns_similar_case_after_add():
    test_id = 999999
    client = cases._get_client()
    try:
        cases.add_case(
            test_id,
            "Edge-Ring defect caused by etch chamber pressure drift",
            {"defect_class": "Edge-Ring", "action": "recalibrate chamber pressure sensor"},
        )
        hits = cases.search_cases("Edge-Ring etch pressure issue", top_k=1)
        assert hits
        assert hits[0]["defect_class"] == "Edge-Ring"
    finally:
        client.delete(collection_name=cases.COLLECTION, points_selector=[test_id])


def test_search_cases_empty_collection_returns_empty_list():
    # collection is kept empty by convention (case data backfilled later) -
    # a query with no indexed points must degrade gracefully, not error.
    hits = cases.search_cases("some defect nobody has logged yet", top_k=3)
    assert isinstance(hits, list)
