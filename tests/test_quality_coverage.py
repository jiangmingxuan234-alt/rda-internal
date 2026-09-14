from rda.quality.coverage import fixed_grid_coverage
def test_fixed_grid_requires_explicit_bounds_and_uses_same_grid():
    assert fixed_grid_coverage([(0,)], None).status=="UNASSESSED"
    x=fixed_grid_coverage([(0.1,), (0.9,)], {"bounds":[(0,1)],"bins":[2],"units":["m"],"frame":"base"})
    assert x.total_bins==2 and x.occupancy_ratio==1.0
