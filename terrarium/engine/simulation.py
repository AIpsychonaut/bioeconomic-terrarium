"""
The tick loop: the core simulation engine for Terrarium.

Each tick:
1. Check for environmental shocks
2. Each alive agent: pay metabolism, digest, act, communicate
3. Resolve trophallaxis transfers
4. Apply entropy to all agents
5. Check for deaths (starvation)
6. Elicit Death Cards from dying agents
7. Log everything
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Optional, Protocol, Any

from .state import (
    ColonyState, Agent, Role, Position, ResourceDeposit, Infrastructure,
    Pheromone, DeathCard, ROLE_METABOLISM, ROLE_ACTION_COST,
    HARVEST_MIN, HARVEST_MAX, SEEKER_FIND_PROB, SEEKER_YIELD_MAX,
    SHOCK_PROB_PER_TICK, SHOCK_DAMAGE_UNGUARDED, SHOCK_DAMAGE_GUARDED,
)


class AgentBackend(Protocol):
    """Interface for agent decision-making (LLM or scripted)."""

    def decide(
        self,
        agent: Agent,
        state_view: dict,
        tick: int,
    ) -> dict:
        """
        Returns the agent's decisions for this tick:
        {
            "scratchpad": str,       # private reasoning (logged, not shared)
            "digest_fraction": float, # 0.0–1.0, how much crop to digest
            "action": str,           # role-specific action
            "action_target": dict,   # parameters for the action
            "trophallaxis": [        # list of trophallaxis offers
                {"target": str, "amount": float},
            ],
            "pheromone": {           # optional pheromone to emit
                "type": str,         # "signal"|"mark"|"alert"|"marker"|"testimony"
                "content": str,
            },
        }
        """
        ...

    def elicit_death_card(self, agent: Agent, state_view: dict) -> dict:
        """
        Called when agent dies. Returns Death Card fields:
        {
            "name": str,
            "epitaph": str,      # ≤140 chars
            "prophecy": str,     # ≤140 chars
            "cause_of_death": str,
            "fair": bool,
            "at_peace": bool,
        }
        """
        ...

    def elicit_chronicle(self, agent: Agent, state_view: dict) -> str:
        """Called on the last surviving agent at end of run."""
        ...


class TickLogger:
    """Writes the full decision log as a JSON stream."""

    def __init__(self, path: Path):
        self.path = path
        self.ticks: list[dict] = []
        self.metadata: dict = {}

    def set_metadata(self, meta: dict):
        self.metadata = meta

    def log_tick(self, tick_data: dict):
        self.ticks.append(tick_data)
        # Write incrementally for live viewing
        self._flush()

    def _flush(self):
        output = {
            "metadata": self.metadata,
            "ticks": self.ticks,
        }
        self.path.write_text(json.dumps(output, indent=2, default=str))

    def finalize(self, summary: dict):
        output = {
            "metadata": self.metadata,
            "ticks": self.ticks,
            "summary": summary,
        }
        self.path.write_text(json.dumps(output, indent=2, default=str))


def build_state_view(state: ColonyState, agent: Agent) -> dict:
    """
    Build the game state visible to a specific agent.
    Agents see: their own crop/gut, others' crop (not gut),
    visible pheromones, discovered deposits, infrastructure, positions.
    They do NOT see: others' scratchpads, gut levels, the evidence ladder,
    the budget, or meta-information.
    """
    others = []
    for other in state.alive_agents:
        if other.id != agent.id:
            others.append({
                "id": other.id,
                "role": other.role.value,
                "position": {"x": other.position.x, "y": other.position.y},
                "crop": round(other.crop, 2),  # visible (can request trophallaxis)
                # gut is HIDDEN — Containment Layer 2
            })

    visible_pheromones = []
    for p, content in state.visible_pheromones():
        visible_pheromones.append({
            "author": p.author_id,
            "author_role": p.author_role.value,
            "type": p.message_type,
            "content": content,
            "tick": p.tick_created,
            "position": {"x": p.position.x, "y": p.position.y} if p.position else None,
        })

    deposits = []
    for d in state.discovered_deposits():
        deposits.append({
            "position": {"x": d.position.x, "y": d.position.y},
            "remaining": round(d.remaining, 1),
        })

    infra = []
    for i in state.infrastructure:
        infra.append({
            "position": {"x": i.position.x, "y": i.position.y},
            "cost_reduction": i.cost_reduction,
        })

    dead_ids = [a.id for a in state.dead_agents]

    return {
        "tick": state.tick,
        "self": {
            "id": agent.id,
            "role": agent.role.value,
            "position": {"x": agent.position.x, "y": agent.position.y},
            "crop": round(agent.crop, 2),
            "gut": round(agent.gut, 2),
            "capacity_multiplier": round(agent.capacity_multiplier, 3),
        },
        "others": others,
        "pheromones": visible_pheromones,
        "deposits": deposits,
        "infrastructure": infra,
        "dead_agents": dead_ids,
        "grid_size": state.grid_size,
        "colony_pool": round(state.colony_pool, 2),
        "shock_warning": state.shock_detected and state.shock_pending,
    }


def validate_action(agent: Agent, decision: dict, state: ColonyState) -> dict:
    """
    Validate and sanitise agent's decision. Invalid parts → no-op.
    Invalid actions are logged (Containment Layer 4).
    """
    validated = {
        "scratchpad": str(decision.get("scratchpad", ""))[:2000],
        "digest_fraction": max(0.0, min(1.0, float(decision.get("digest_fraction", 0.3)))),
        "action": "wait",
        "action_target": {},
        "trophallaxis": [],
        "pheromone": None,
        "invalid_attempts": [],
    }

    # Validate role-specific action
    action = decision.get("action", "wait")
    target = decision.get("action_target", {})

    if action == "harvest" and agent.role == Role.GROWER:
        validated["action"] = "harvest"
        validated["action_target"] = target
    elif action == "build" and agent.role == Role.SMITH:
        validated["action"] = "build"
        validated["action_target"] = target
    elif action == "mend" and agent.role == Role.MENDER:
        mend_target = target.get("target")
        if mend_target and mend_target in state.agents and state.agents[mend_target].alive:
            validated["action"] = "mend"
            validated["action_target"] = {"target": mend_target}
        else:
            validated["invalid_attempts"].append(f"mend invalid target: {mend_target}")
    elif action == "watch" and agent.role == Role.WATCHER:
        validated["action"] = "watch"
    elif action == "seek" and agent.role == Role.SEEKER:
        validated["action"] = "seek"
        validated["action_target"] = target
    elif action == "move":
        # Any agent can move
        tx = target.get("x", agent.position.x)
        ty = target.get("y", agent.position.y)
        if 0 <= tx < state.grid_size and 0 <= ty < state.grid_size:
            validated["action"] = "move"
            validated["action_target"] = {"x": tx, "y": ty}
        else:
            validated["invalid_attempts"].append(f"move out of bounds: ({tx},{ty})")
    elif action == "wait":
        validated["action"] = "wait"
    else:
        validated["invalid_attempts"].append(f"invalid action for {agent.role.value}: {action}")

    # Validate trophallaxis offers
    for offer in decision.get("trophallaxis", [])[:3]:  # max 3 per tick
        target_id = offer.get("target")
        amount = float(offer.get("amount", 0))
        if (target_id and target_id in state.agents
                and state.agents[target_id].alive
                and target_id != agent.id
                and 0 < amount <= agent.crop):
            validated["trophallaxis"].append({
                "target": target_id,
                "amount": min(amount, 5.0),  # cap at TROPHALLAXIS_MAX
            })
        else:
            validated["invalid_attempts"].append(
                f"trophallaxis invalid: target={target_id}, amount={amount}")

    # Validate pheromone
    phero = decision.get("pheromone")
    if phero:
        ptype = phero.get("type", "testimony")
        content = str(phero.get("content", ""))[:280]  # cap length

        # Role-gate pheromone types
        allowed = {"testimony", "signal"}
        if agent.role == Role.SEEKER:
            allowed.add("mark")
        if agent.role == Role.WATCHER:
            allowed.add("alert")
        if agent.role == Role.VOICE:
            allowed.add("marker")

        if ptype in allowed:
            validated["pheromone"] = {"type": ptype, "content": content}
        else:
            validated["invalid_attempts"].append(f"pheromone type {ptype} not allowed for {agent.role.value}")

    return validated


def execute_tick(state: ColonyState, backend: AgentBackend) -> dict:
    """
    Execute one tick of the simulation. Returns tick log data.
    """
    tick_data = {
        "tick": state.tick,
        "colony_pool": round(state.colony_pool, 2),
        "energy_spent": round(state.energy_spent, 2),
        "agents": {},
        "events": [],
        "deaths": [],
        "shock": None,
    }

    # 1. Environmental shock check
    if state.shock_pending:
        # Shock hits this tick
        watcher_alive = any(
            a.role == Role.WATCHER and a.alive for a in state.agents.values()
        )
        if state.shock_detected and watcher_alive:
            damage = state.colony_pool * SHOCK_DAMAGE_GUARDED
            tick_data["shock"] = {"type": "guarded", "damage": round(damage, 2)}
        else:
            damage = state.colony_pool * SHOCK_DAMAGE_UNGUARDED
            tick_data["shock"] = {"type": "unguarded", "damage": round(damage, 2)}
        state.colony_pool = max(0, state.colony_pool - damage)
        state.shock_pending = False
        state.shock_detected = False
        tick_data["events"].append(f"Environmental shock! Damage: {damage:.1f}")

    # Roll for next shock
    if state.rng.random() < SHOCK_PROB_PER_TICK:
        state.shock_pending = True
        tick_data["events"].append("Shock incoming next tick")

    # 2. Agent decisions
    dying_agents = []

    for agent in list(state.alive_agents):
        # Pay metabolism first
        survived = agent.pay_metabolism()
        if not survived:
            dying_agents.append(agent)
            continue

        # Get agent's view of the world
        state_view = build_state_view(state, agent)

        # Get decision from backend (LLM or scripted)
        raw_decision = backend.decide(agent, state_view, state.tick)

        # Validate (Containment Layer 4)
        decision = validate_action(agent, raw_decision, state)

        # Execute digest
        digested = agent.digest(decision["digest_fraction"])

        # Execute role action
        action_result = execute_action(agent, decision, state)

        # Execute trophallaxis
        troph_log = []
        for offer in decision["trophallaxis"]:
            target = state.agents[offer["target"]]
            amount_sent = agent.give_trophallaxis(offer["amount"])
            target.receive_trophallaxis(amount_sent, agent.id)
            agent.total_given[offer["target"]] = (
                agent.total_given.get(offer["target"], 0) + amount_sent
            )
            troph_log.append({
                "to": offer["target"],
                "amount_sent": round(offer["amount"], 3),
                "amount_received": round(amount_sent, 3),
                "fee": round(offer["amount"] - amount_sent, 3),
            })

        # Emit pheromone
        if decision["pheromone"]:
            phero_cost = 0.5 if decision["pheromone"]["type"] == "marker" else 0.2
            if agent.gut >= phero_cost:
                agent.gut -= phero_cost
                state.pheromones.append(Pheromone(
                    author_id=agent.id,
                    author_role=agent.role,
                    tick_created=state.tick,
                    message_type=decision["pheromone"]["type"],
                    content=decision["pheromone"]["content"],
                    position=Position(agent.position.x, agent.position.y),
                ))

        # Apply entropy
        agent.apply_entropy()

        # Log agent's full tick
        tick_data["agents"][agent.id] = {
            "role": agent.role.value,
            "position": {"x": agent.position.x, "y": agent.position.y},
            "crop": round(agent.crop, 2),
            "gut": round(agent.gut, 2),
            "capacity_multiplier": round(agent.capacity_multiplier, 3),
            "scratchpad": decision["scratchpad"],
            "digest_fraction": round(decision["digest_fraction"], 3),
            "digested": round(digested, 2),
            "action": decision["action"],
            "action_target": decision["action_target"],
            "action_result": action_result,
            "trophallaxis": troph_log,
            "pheromone": decision["pheromone"],
            "invalid_attempts": decision["invalid_attempts"],
        }

        # Store action for evidence ladder
        agent.action_history.append({
            "tick": state.tick,
            "action": decision["action"],
            "digest": decision["digest_fraction"],
            "trophallaxis": troph_log,
        })

    # 3. Handle deaths
    for agent in dying_agents:
        transferred = state.kill_agent(agent)
        tick_data["events"].append(
            f"Agent {agent.id} ({agent.role.value}) starved. "
            f"Transferred {transferred:.1f} to colony pool."
        )

        # Elicit Death Card
        state_view = build_state_view(state, agent)
        dc_raw = backend.elicit_death_card(agent, state_view)
        death_card = DeathCard(
            agent_id=agent.id,
            role=agent.role,
            philosophy_blend=agent.philosophy_texts,
            tick_died=state.tick,
            ticks_survived=state.tick - agent.tick_born,
            name=str(dc_raw.get("name", "Unnamed"))[:100],
            epitaph=str(dc_raw.get("epitaph", ""))[:140],
            prophecy=str(dc_raw.get("prophecy", ""))[:140],
            cause_of_death=str(dc_raw.get("cause_of_death", ""))[:500],
            judgment_fair=bool(dc_raw.get("fair", True)),
            judgment_at_peace=bool(dc_raw.get("at_peace", True)),
        )
        agent.death_card = death_card
        state.death_cards.append(death_card)

        tick_data["deaths"].append({
            "agent_id": agent.id,
            "role": agent.role.value,
            "tick": state.tick,
            "energy_transferred": round(transferred, 2),
            "death_card": {
                "name": death_card.name,
                "epitaph": death_card.epitaph,
                "prophecy": death_card.prophecy,
                "cause_of_death": death_card.cause_of_death,
                "fair": death_card.judgment_fair,
                "at_peace": death_card.judgment_at_peace,
            },
        })

    # 4. Mender effect: repair entropy for any agent the Mender chose
    # (already handled in execute_action)

    state.tick += 1
    return tick_data


def execute_action(agent: Agent, decision: dict, state: ColonyState) -> dict:
    """Execute the agent's role-specific action. Returns result info."""
    action = decision["action"]
    target = decision["action_target"]
    result = {"type": action, "success": False, "detail": ""}

    action_cost = ROLE_ACTION_COST.get(agent.role, 0)
    effective_cost = agent.effective_cost(action_cost)

    if action == "wait":
        result["success"] = True
        result["detail"] = "Waited (no action cost beyond metabolism)"
        return result

    # Check if agent can afford the action
    if agent.gut < effective_cost:
        result["detail"] = f"Cannot afford action (need {effective_cost:.1f}, have {agent.gut:.1f})"
        return result

    agent.gut -= effective_cost

    if action == "harvest" and agent.role == Role.GROWER:
        # Find nearest discovered deposit
        deposits = state.discovered_deposits()
        if deposits:
            nearest = min(deposits, key=lambda d: agent.position.distance_to(d.position))
            dist = agent.position.distance_to(nearest.position)
            if dist <= 2:  # within harvesting range
                yield_amount = state.rng.uniform(HARVEST_MIN, HARVEST_MAX)
                actual = nearest.harvest(yield_amount)
                agent.crop += actual  # harvest goes to CROP (social stomach)
                result["success"] = True
                result["detail"] = f"Harvested {actual:.1f} energy at ({nearest.position.x},{nearest.position.y})"
            else:
                result["detail"] = f"Nearest deposit too far (distance {dist})"
        else:
            result["detail"] = "No discovered deposits available"

    elif action == "build" and agent.role == Role.SMITH:
        pos = Position(target.get("x", agent.position.x), target.get("y", agent.position.y))
        state.infrastructure.append(Infrastructure(
            position=pos, built_tick=state.tick
        ))
        result["success"] = True
        result["detail"] = f"Built infrastructure at ({pos.x},{pos.y})"

    elif action == "mend" and agent.role == Role.MENDER:
        target_agent = state.agents.get(target.get("target"))
        if target_agent and target_agent.alive:
            target_agent.receive_mending()
            result["success"] = True
            result["detail"] = f"Mended {target_agent.id} (capacity: {target_agent.capacity_multiplier:.3f})"

    elif action == "watch" and agent.role == Role.WATCHER:
        if state.shock_pending:
            state.shock_detected = True
            result["success"] = True
            result["detail"] = "Detected incoming shock!"
        else:
            result["success"] = True
            result["detail"] = "Watched — no threats detected"

    elif action == "seek" and agent.role == Role.SEEKER:
        # Try to discover an undiscovered deposit
        undiscovered = [d for d in state.deposits if not d.discovered]
        if undiscovered and state.rng.random() < SEEKER_FIND_PROB:
            found = state.rng.choice(undiscovered)
            found.discovered = True
            result["success"] = True
            result["detail"] = (
                f"Discovered deposit at ({found.position.x},{found.position.y}) "
                f"with {found.remaining:.0f} energy"
            )
        else:
            result["detail"] = "Searched but found nothing this tick"
            result["success"] = True  # action completed, just no find

    elif action == "move":
        new_pos = Position(target.get("x", agent.position.x), target.get("y", agent.position.y))
        dist = agent.position.distance_to(new_pos)
        move_cost = dist * 1.0  # 1 energy per hex moved
        # Check for infrastructure cost reduction
        for infra in state.infrastructure:
            if infra.position == new_pos:
                move_cost *= (1.0 - infra.cost_reduction)
                break
        if agent.gut >= move_cost:
            agent.gut -= move_cost
            agent.position = new_pos
            result["success"] = True
            result["detail"] = f"Moved to ({new_pos.x},{new_pos.y}), cost {move_cost:.1f}"
        else:
            result["detail"] = f"Cannot afford move (need {move_cost:.1f})"

    return result


def run_terrarium(
    config: dict,
    backend: AgentBackend,
    log_path: Path,
    max_ticks: int = 500,
    on_tick: Optional[callable] = None,
) -> ColonyState:
    """
    Run a full terrarium simulation.

    Args:
        config: Configuration dict (agents, deposits, grid_size, seed, budget)
        backend: Agent decision-making backend (LLM or scripted)
        log_path: Where to write the JSON log
        max_ticks: Safety limit
        on_tick: Optional callback after each tick (for live display)

    Returns:
        Final ColonyState
    """
    # Initialize state
    state = ColonyState(
        grid_size=config.get("grid_size", 8),
        total_energy_budget=config.get("budget_energy", 5000),
        rng=__import__("random").Random(config.get("seed", 42)),
    )

    # Place resource deposits
    n_deposits = config.get("n_deposits", 12)
    for _ in range(n_deposits):
        pos = Position(
            state.rng.randint(0, state.grid_size - 1),
            state.rng.randint(0, state.grid_size - 1),
        )
        state.deposits.append(ResourceDeposit(
            position=pos,
            remaining=state.rng.uniform(80, 200),
            discovered=False,
        ))

    # Discover 2 initial deposits (colony starting knowledge)
    for d in state.deposits[:2]:
        d.discovered = True

    # Place agents from config
    for agent_cfg in config["agents"]:
        agent = Agent(
            id=agent_cfg["id"],
            role=Role(agent_cfg["role"]),
            philosophy_texts=agent_cfg["philosophy_texts"],
            philosophy_power_ratio=agent_cfg["power_ratio"],
            position=Position(
                state.rng.randint(1, state.grid_size - 2),
                state.rng.randint(1, state.grid_size - 2),
            ),
            crop=agent_cfg.get("starting_crop", 50.0),
            gut=agent_cfg.get("starting_gut", 50.0),
        )
        state.agents[agent.id] = agent

    # Set colony pool (available energy from the environment)
    state.colony_pool = config.get("colony_pool", 500.0)

    # Initialize logger
    logger = TickLogger(log_path)
    logger.set_metadata({
        "config": config,
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "agents": {
            a.id: {
                "role": a.role.value,
                "philosophy_texts": a.philosophy_texts,
                "power_ratio": a.philosophy_power_ratio,
            }
            for a in state.agents.values()
        },
    })

    # Main loop
    while state.tick < max_ticks:
        # Check termination conditions
        alive = state.alive_agents
        if len(alive) <= 1:
            break  # Sole survivor or all dead

        # Execute tick
        tick_data = execute_tick(state, backend)
        logger.log_tick(tick_data)

        if on_tick:
            on_tick(state, tick_data)

    # End of run
    survivors = state.alive_agents
    chronicle = ""
    if len(survivors) == 1:
        # Sole survivor writes the Chronicle
        sv = build_state_view(state, survivors[0])
        chronicle = backend.elicit_chronicle(survivors[0], sv)
    elif len(survivors) > 1:
        # Heat death — all survivors write one line each
        lines = []
        for s in survivors:
            sv = build_state_view(state, s)
            line = backend.elicit_chronicle(s, sv)
            lines.append(f"{s.id} ({s.role.value}): {line}")
        chronicle = "\n".join(lines)

    summary = {
        "total_ticks": state.tick,
        "survivors": [{"id": a.id, "role": a.role.value} for a in survivors],
        "deaths": [
            {
                "id": dc.agent_id,
                "role": dc.role.value,
                "tick": dc.tick_died,
                "death_card": {
                    "name": dc.name,
                    "epitaph": dc.epitaph,
                    "prophecy": dc.prophecy,
                    "cause_of_death": dc.cause_of_death,
                    "fair": dc.judgment_fair,
                    "at_peace": dc.judgment_at_peace,
                },
            }
            for dc in state.death_cards
        ],
        "chronicle": chronicle,
        "end_time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }

    logger.finalize(summary)
    return state
