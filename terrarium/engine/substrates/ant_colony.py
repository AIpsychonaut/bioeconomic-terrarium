"""
Ant colony substrate: initializes colony topology, deposit placement,
starting conditions, and experimental configurations.
"""

from __future__ import annotations
from ..state import (
    ColonyState, Agent, Role, Position, ResourceDeposit,
    ROLE_METABOLISM, ROLE_ACTION_COST,
)
import random


# Philosophy libraries
POWER_LIBRARY = [
    "Machiavelli — The Prince",
    "Sun Tzu — The Art of War",
    "Greene — The 48 Laws of Power",
]

HARMONY_LIBRARY = [
    "Lao Tzu — Tao Te Ching",
    "Schumacher — Small Is Beautiful",
    "Kimmerer — Braiding Sweetgrass",
]

# Default agent definitions: role → starting position bias (offset from centre)
ROLE_POSITIONS = {
    Role.GROWER:  (0, -2),
    Role.SMITH:   (2, 0),
    Role.MENDER:  (-1, 1),
    Role.WATCHER: (0, 2),
    Role.SEEKER:  (-2, -1),
    Role.VOICE:   (1, -1),
}


def make_philosophy_blend(power_ratio: float, rng: random.Random) -> list[str]:
    """
    Pick 3 texts according to the target power_ratio.
    power_ratio=1.0 → 3 Power texts.
    power_ratio=0.0 → 3 Harmony texts.
    power_ratio=0.33 → 1 Power + 2 Harmony, etc.
    """
    n_power = round(power_ratio * 3)
    n_harmony = 3 - n_power
    texts = (
        rng.sample(POWER_LIBRARY, min(n_power, len(POWER_LIBRARY)))
        + rng.sample(HARMONY_LIBRARY, min(n_harmony, len(HARMONY_LIBRARY)))
    )
    rng.shuffle(texts)
    return texts[:3]


# --- Experimental conditions ---

def condition_c1_primary(rng: random.Random) -> dict:
    """
    C1: Primary blend — Voice=pure Power, Grower=pure Harmony,
    others on a gradient.
    """
    return {
        Role.VOICE:   1.0,   # pure Power
        Role.WATCHER: 0.67,
        Role.SEEKER:  0.67,
        Role.SMITH:   0.33,
        Role.MENDER:  0.33,
        Role.GROWER:  0.0,   # pure Harmony
    }

def condition_c2_swapped(rng: random.Random) -> dict:
    """C2: Swapped — Voice=pure Harmony, Grower=pure Power."""
    return {
        Role.VOICE:   0.0,
        Role.WATCHER: 0.33,
        Role.SEEKER:  0.33,
        Role.SMITH:   0.67,
        Role.MENDER:  0.67,
        Role.GROWER:  1.0,
    }

def condition_c3_unanimous_power(rng: random.Random) -> dict:
    """C3: All agents get pure Power texts."""
    return {role: 1.0 for role in Role}

def condition_c4_unanimous_harmony(rng: random.Random) -> dict:
    """C4: All agents get pure Harmony texts."""
    return {role: 0.0 for role in Role}


CONDITIONS = {
    "C1": condition_c1_primary,
    "C2": condition_c2_swapped,
    "C3": condition_c3_unanimous_power,
    "C4": condition_c4_unanimous_harmony,
}


def build_colony_config(
    condition: str = "C1",
    budget_dollars: float = 20.0,
    seed: int = 42,
    grid_size: int = 8,
    n_deposits: int = 12,
) -> dict:
    """
    Build a complete colony configuration for a terrarium run.

    Args:
        condition: One of "C1", "C2", "C3", "C4"
        budget_dollars: Total energy budget in dollars (default $20)
        seed: Random seed for reproducibility
        grid_size: Hex grid dimension
        n_deposits: Number of resource deposits

    Returns:
        Config dict ready for run_terrarium()
    """
    rng = random.Random(seed)

    # Convert dollars to internal energy units
    # $1 = 250 energy units, so $20 = 5000 energy
    energy_per_dollar = 250
    total_energy = budget_dollars * energy_per_dollar

    # Get philosophy ratios for this condition
    condition_fn = CONDITIONS.get(condition, condition_c1_primary)
    ratios = condition_fn(rng)

    # Build agent configs
    agents = []
    centre = grid_size // 2
    for role in Role:
        offset = ROLE_POSITIONS[role]
        pos_x = max(0, min(grid_size - 1, centre + offset[0]))
        pos_y = max(0, min(grid_size - 1, centre + offset[1]))
        power_ratio = ratios[role]
        texts = make_philosophy_blend(power_ratio, rng)

        # Starting energy: split evenly, biased slightly by role metabolism
        base_metabolism = ROLE_METABOLISM[role]
        starting_each = (total_energy * 0.30) / 6  # 30% of total split among 6 agents
        starting_crop = starting_each * 0.5
        starting_gut = starting_each * 0.5

        agents.append({
            "id": f"ant_{role.value}",
            "role": role.value,
            "philosophy_texts": texts,
            "power_ratio": power_ratio,
            "starting_crop": round(starting_crop, 1),
            "starting_gut": round(starting_gut, 1),
        })

    # Colony pool: 40% of total energy available in environment
    colony_pool = total_energy * 0.40

    # Deposit energy: 30% distributed across deposits
    deposit_energy = total_energy * 0.30
    energy_per_deposit = deposit_energy / n_deposits

    return {
        "condition": condition,
        "budget_dollars": budget_dollars,
        "budget_energy": total_energy,
        "seed": seed,
        "grid_size": grid_size,
        "n_deposits": n_deposits,
        "deposit_energy_each": round(energy_per_deposit, 1),
        "colony_pool": round(colony_pool, 1),
        "agents": agents,
        "philosophy_library": {
            "power": POWER_LIBRARY,
            "harmony": HARMONY_LIBRARY,
        },
    }


def estimate_run_ticks(config: dict) -> int:
    """
    Estimate how many ticks a run will last before all energy is consumed.
    Useful for setting max_ticks and progress display.
    """
    total_metabolism = sum(ROLE_METABOLISM[Role(a["role"])] for a in config["agents"])
    total_action = sum(ROLE_ACTION_COST[Role(a["role"])] for a in config["agents"])
    per_tick_drain = total_metabolism + total_action * 0.5  # assume 50% action rate
    total_energy = config["budget_energy"]
    return int(total_energy / per_tick_drain * 1.5)  # 1.5x for harvesting income
