from rda.quality.distribution import map_task, summarize_measurements, merge_grouped_summaries
from rda.quality.contracts import *
def test_task_mapping_preserves_raw_values_and_unknown_mapping():
    x=map_task(3,"原始",{3:"mapped"},"v1"); assert x["task"]=="原始" and x["mapped_task"]=="mapped"
def test_summary_merge_deduplicates_episode():
    r=MeasurementRecord("u","m","v","sha256:"+"a"*64,Applicability.APPLICABLE,{"planned_samples":1,"attempted_samples":1,"computed_samples":1},{},())
    a=summarize_measurements([r],{"u":{"episode_id":"e"}}); b=summarize_measurements([r],{"u":{"episode_id":"e"}})
    x=merge_grouped_summaries([a,b]); assert list(x.groups.values())[0]["episode_count"]==1
