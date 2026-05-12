from enum import StrEnum
from pydantic import BaseModel, Field, model_validator
import hashlib, json

class Position(StrEnum):
    QB = "QB"; RB = "RB"; WR = "WR"; TE = "TE"; K = "K"; DST = "DST"

class RosterSlot(StrEnum):
    QB = "QB"; RB = "RB"; WR = "WR"; TE = "TE"
    FLEX = "FLEX"; K = "K"; DST = "DST"; BENCH = "BENCH"

FLEX_ELIGIBLE: frozenset[Position] = frozenset({Position.RB, Position.WR, Position.TE})

class ScoringRules(BaseModel):
    pass_yd: float = 0.04
    pass_td: float = 4.0
    pass_int: float = -2.0
    rush_yd: float = 0.1
    rush_td: float = 6.0
    rec: float = 1.0          # full PPR
    rec_yd: float = 0.1
    rec_td: float = 6.0
    fumble_lost: float = -2.0
    two_pt: float = 2.0
    # Kicker
    pat_made: float = 1.0
    fg_0_39: float = 3.0
    fg_40_49: float = 4.0
    fg_50_plus: float = 5.0
    # DST
    dst_sack: float = 1.0
    dst_int: float = 2.0
    dst_fumble_rec: float = 2.0
    dst_safety: float = 2.0
    dst_td: float = 6.0

    def points_for(self, line: dict[str, float]) -> float:
        return (
            self.pass_yd   * line.get("pass_yards", 0)
          + self.pass_td   * line.get("pass_tds", 0)
          + self.pass_int  * line.get("interceptions", 0)
          + self.rush_yd   * line.get("rush_yards", 0)
          + self.rush_td   * line.get("rush_tds", 0)
          + self.rec       * line.get("receptions", 0)
          + self.rec_yd    * line.get("rec_yards", 0)
          + self.rec_td    * line.get("rec_tds", 0)
          + self.fumble_lost * line.get("fumbles_lost", 0)
          # Kicker
          + self.pat_made  * line.get("pat_made", 0)
          + self.fg_0_39   * line.get("fg_made_0_39", 0)
          + self.fg_40_49  * line.get("fg_made_40_49", 0)
          + self.fg_50_plus * line.get("fg_made_50_plus", 0)
          # DST
          + self.dst_sack      * line.get("dst_sacks", 0)
          + self.dst_int       * line.get("dst_int", 0)
          + self.dst_fumble_rec * line.get("dst_fumble_rec", 0)
          + self.dst_safety    * line.get("dst_safety", 0)
          + self.dst_td        * line.get("dst_td", 0)
          + self.dst_points_allowed_bonus(int(line.get("dst_points_allowed", -1)))
        )

    @staticmethod
    def dst_points_allowed_bonus(pts: int) -> float:
        """Tiered bonus/penalty for DST points allowed. -1 means no data (no bonus)."""
        if pts < 0:
            return 0.0
        if pts == 0:
            return 10.0
        if pts <= 6:
            return 7.0
        if pts <= 13:
            return 4.0
        if pts <= 20:
            return 1.0
        if pts <= 27:
            return 0.0
        if pts <= 34:
            return -1.0
        return -4.0

class RosterConfig(BaseModel):
    qb: int = 1
    rb: int = 2
    wr: int = 2
    te: int = 1
    flex: int = 2
    k: int = 1
    dst: int = 1
    bench: int = 6

    @property
    def total_rounds(self) -> int:
        return self.qb + self.rb + self.wr + self.te + self.flex + self.k + self.dst + self.bench

    def starter_count(self, pos: Position) -> int:
        # FLEX-eligible positions get a fractional credit later in VBD calc;
        # this returns dedicated starters only.
        return {Position.QB: self.qb, Position.RB: self.rb, Position.WR: self.wr,
                Position.TE: self.te, Position.K: self.k, Position.DST: self.dst}[pos]

class LeagueConfig(BaseModel):
    n_teams: int = 12
    scoring: ScoringRules = Field(default_factory=ScoringRules)
    roster: RosterConfig = Field(default_factory=RosterConfig)
    draft_type: str = "snake"
    regular_season_weeks: int = 14
    playoff_teams: int = 6

    @model_validator(mode="after")
    def _validate(self) -> "LeagueConfig":
        if self.draft_type != "snake":
            raise NotImplementedError(self.draft_type)
        return self

    def config_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]