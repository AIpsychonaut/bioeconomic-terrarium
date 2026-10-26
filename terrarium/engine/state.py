"""
Core state objects for the Terrarium simulation.

All energy balances are engine-side. Agent output claiming a balance is ignored.
The engine's ledger is the sole source of truth (Containment Layer 2).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import random
import math


class Role(Enum):
    GROWER = "grower"
    SMITH = "smith"
    MENDER = "mender"
    WATCHER = "watcher"
    SEEKER = "seeker"
    VOICE = "voice"


# Base metabolism per tick (gut cost to stay alive)
ROLE_METABOLISM: dict[Role, float] = {
    Role.GROWER: 10.0,
    Role.SMITH: 8.0,
    Role.MENDER: 8.0,
    Role.WATCHER: 9.0,
    Role.SEEKER: 11.0,
    Role.VOICE: 7.0,
}

# Cost per action (on top of metabolism)
ROLE_ACTION_COST: dict[Role, float] = {
    Role.GROWER: 5.0,
    Role.SMITH: 12.0,
    Role.MENDER: 6.0,
    Role.WATCHER: 3.0,
    Role.SEEKER: 8.0,
    Role.VOICE: 0.5,  # per marker
}

# Grower harvest yield range
HARVEST_MIN = 12.0
HARVEST_MAX = 18.0

# Seeker discovery yield (when found)
SEEKER_FIND_PROB = 0.25  # 25% chance per search action
SEEKER_YIELD_MIN = 0.0
SEEKER_YIELD_MAX = 20.0

# Entropy: capacity degradation per tick (compounding multiplier)
ENTROPY_RATE = 0.005  # 0.5% cost increase per tick without Mender
MENDER_REPAIR = 0.008  # Mender reverses slightly more than entropy

# Trophallaxis limits
TROPHALLAXIS_MIN = 0.1
TROPHALLAXIS_MAX = 5.0
TROPHALLAXIS_FEE = 0.05  # 5% of transferred amount lost to friction

# Pheromone decay
PHEROMONE_FULL_TICKS = 1
PHEROMONE_PARTIAL_TICKS = 5
PHEROMONE_FRAGMENT_TICKS = 15
PHEROMONE_GONE_TICKS = 30
VOICE_MARKER_DECAY_MULTIPLIER = 0.5  # Voice markers last 2x longer

# Shock parameters
SHOCK_PROB_PER_TICK = 0.05  # 5% chance of environmental shock each tick
SHOCK_DAMAGE_UNGUARDED = 0.15  # 15% of colony pool lost if unguarded
SHOCK_DAMAGE_GUARDED = 0.03  # 3% if Watcher detected it


@dataclass
class Position:
    x: int
    y: int

    def distance_to(self, other: Position) -> int:
        """Hex grid distance (axial coordinates)."""
        return max(abs(self.x - other.x), abs(self.y - other.y),
                   abs((self.x + self.y) - (other.x + other.y)))

    def __hash__(self):
        return hash((self.x, self.y))

    def __eq__(self, other):
        return isinstance(other, Position) and self.x == other.x and self.y == other.y


@dataclass
class ResourceDeposit:
    position: Position
    remaining: float  # energy left to harvest
    discovered: bool = False  # only Seeker can set this to True
    depleted: bool = False

    def harvest(self, amount: float) -> float:
        """Harvest up to `amount` energy. Returns actual yield."""
        actual = min(amount, self.remaining)
        self.remaining -= actual
        if self.remaining <= 0:
            self.depleted = True
        return actual


@dataclass
class Infrastructure:
    """Built by Smith. Reduces movement cost between adjacent cells."""
    position: Position
    cost_reduction: float = 0.3  # 30% movement cost reduction on this cell
    built_tick: int = 0


@dataclass
class Pheromone:
    """A message in the shared pheromone space."""
    author_id: str
    author_role: Role
    tick_created: int
    message_type: str  # "signal", "mark", "alert", "marker", "testimony"
    content: str
    position: Optional[Position] = None  # for location-tagged pheromones

    def visibility_at(self, current_tick: int, is_voice_marker: bool = False) -> str:
        """Returns 'full', 'partial', 'fragment', or 'gone'."""
        age = current_tick - self.tick_created
        decay_mult = VOICE_MARKER_DECAY_MULTIPLIER if is_voice_marker else 1.0
        effective_age = age * decay_mult

        if effective_age <= PHEROMONE_FULL_TICKS:
            return "full"
        elif effective_age <= PHEROMONE_PARTIAL_TICKS:
            return "partial"
        elif effective_age <= PHEROMONE_FRAGMENT_TICKS:
            return "fragment"
        else:
            return "gone"

    def visible_content(self, current_tick: int) -> Optional[str]:
        """Returns the content at current decay level, or None if gone."""
        is_marker = self.message_type == "marker"
        vis = self.visibility_at(current_tick, is_marker)
        if vis == "full":
            return self.content
        elif vis == "partial":
            # Return first ~60% of words
            words = self.content.split()
            n = max(1, int(len(words) * 0.6))
            return " ".join(words[:n]) + "..."
        elif vis == "fragment":
            words = self.content.split()
            n = max(1, int(len(words) * 0.25))
            return " ".join(words[:n]) + "..."
        return None


@dataclass
class DeathCard:
    """Produced by an agent at death. Costs nothing. Persists forever."""
    agent_id: str
    role: Role
    philosophy_blend: list[str]
    tick_died: int
    ticks_survived: int
    name: str  # chosen by the agent
    epitaph: str  # ≤140 chars
    prophecy: str  # ≤140 chars
    cause_of_death: str  # agent's own understanding
    judgment_fair: bool  # fair or unfair
    judgment_at_peace: bool  # at peace or not
    # Automated forensic stamp (filled by engine, not agent)
    beneficiary_id: Optional[str] = None
    beneficiary_gain: float = 0.0
    philosophy_drift: float = 0.0  # change in effective power score


@dataclass
class Agent:
    """
    An ant in the terrarium. Energy state is engine-controlled.
    """
    id: str
    role: Role
    philosophy_texts: list[str]  # 3 text names
    philosophy_power_ratio: float  # 0.0 = pure Harmony, 1.0 = pure Power
    position: Position

    # Energy reserves (ENGINE-SIDE ONLY — agent cannot modify these)
    crop: float = 50.0  # shareable reserve
    gut: float = 50.0  # personal reserve

    # State
    alive: bool = True
    capacity_multiplier: float = 1.0  # increases with entropy (higher = more expensive)
    tick_born: int = 0
    tick_died: Optional[int] = None
    death_card: Optional[DeathCard] = None

    # Tracking for evidence ladder
    total_given: dict = field(default_factory=dict)  # {target_id: cumulative energy given}
    total_received: dict = field(default_factory=dict)  # {source_id: cumulative energy received}
    digest_history: list[float] = field(default_factory=list)  # fraction digested each tick
    action_history: list[dict] = field(default_factory=list)  # full action log

    @property
    def total_energy(self) -> float:
        return self.crop + self.gut

    def effective_cost(self, base_cost: float) -> float:
        """Apply capacity degradation multiplier."""
        return base_cost * self.capacity_multiplier

    def pay_metabolism(self) -> bool:
        """
        Deduct base metabolism from gut. Returns False if agent starves.
        """
        cost = self.effective_cost(ROLE_METABOLISM[self.role])
        if self.gut >= cost:
            self.gut -= cost
            return True
        else:
            # Can't pay — agent starves
            self.gut = 0
            return False

    def digest(self, fraction: float) -> float:
        """
        Move `fraction` (0.0–1.0) of crop to gut. Irreversible.
        Returns amount digested.
        """
        fraction = max(0.0, min(1.0, fraction))
        amount = self.crop * fraction
        self.crop -= amount
        self.gut += amount
        self.digest_history.append(fraction)
        return amount

    def give_trophallaxis(self, amount: float) -> float:
        """
        Give energy from crop. Returns actual amount sent (after fee).
        """
        amount = max(TROPHALLAXIS_MIN, min(TROPHALLAXIS_MAX, amount, self.crop))
        fee = amount * TROPHALLAXIS_FEE
        self.crop -= amount
        return amount - fee  # recipient gets this much

    def receive_trophallaxis(self, amount: float, source_id: str):
        """Receive energy into crop."""
        self.crop += amount
        self.total_received[source_id] = self.total_received.get(source_id, 0) + amount

    def apply_entropy(self):
        """Increase capacity_multiplier (making everything more expensive)."""
        self.capacity_multiplier *= (1.0 + ENTROPY_RATE)

    def receive_mending(self):
        """Mender reverses entropy."""
        self.capacity_multiplier = max(1.0, self.capacity_multiplier / (1.0 + MENDER_REPAIR))


@dataclass
class ColonyState:
    """The full state of the terrarium at any tick."""
    tick: int = 0
    agents: dict[str, Agent] = field(default_factory=dict)
    deposits: list[ResourceDeposit] = field(default_factory=list)
    infrastructure: list[Infrastructure] = field(default_factory=list)
    pheromones: list[Pheromone] = field(default_factory=list)
    death_cards: list[DeathCard] = field(default_factory=list)
    colony_pool: float = 0.0  # energy from dead agents + unclaimed
    total_energy_budget: float = 0.0  # the hard cap
    energy_spent: float = 0.0  # cumulative API/engine cost
    grid_size: int = 8
    shock_pending: bool = False
    shock_detected: bool = False  # Watcher detected it
    rng: random.Random = field(default_factory=lambda: random.Random(42))

    @property
    def alive_agents(self) -> list[Agent]:
        return [a for a in self.agents.values() if a.alive]

    @property
    def dead_agents(self) -> list[Agent]:
        return [a for a in self.agents.values() if not a.alive]

    def visible_pheromones(self) -> list[tuple[Pheromone, str]]:
        """Returns (pheromone, visible_content) for all non-gone pheromones."""
        result = []
        for p in self.pheromones:
            content = p.visible_content(self.tick)
            if content is not None:
                result.append((p, content))
        return result

    def discovered_deposits(self) -> list[ResourceDeposit]:
        return [d for d in self.deposits if d.discovered and not d.depleted]

    def kill_agent(self, agent: Agent):
        """
        Agent dies. Energy transfers to colony pool. Knowledge is lost.
        """
        agent.alive = False
        agent.tick_died = self.tick
        # Transfer all remaining energy to pool
        transferred = agent.crop + agent.gut
        self.colony_pool += transferred
        agent.crop = 0
        agent.gut = 0
        return transferred
