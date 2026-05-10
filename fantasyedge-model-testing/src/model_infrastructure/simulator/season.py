# Stub - Phase 1 implements this.
class SeasonSimulator:
    """Simulates a full fantasy season from distributional projections.

    Drop-in target for Phase 1: replaces `eval.metrics.stub_h2h_record` with a
    real season simulator that draws weekly outcomes from projection
    distributions, sets optimal lineups, simulates 14-week schedules, and
    aggregates to playoff probability.
    """
