from selfie.memory_index.base_scorer import BaseScorer
from selfie.memory_index.memory_types import Memory


# TODO: rename this to IdentityScorer
# TODO: query weaviate for certainty instead of distance
# See https://weaviate.io/developers/weaviate/config-refs/distances#distance-vs-certainty
class RelevanceScorer(BaseScorer):
    def __init__(self, score_weight):
        super().__init__(score_weight)

    def calculate_raw_score(self, memory: Memory, certainty: float):
        # TODO use certainty?
        return certainty

    def normalize_score(self, score):
        return score
