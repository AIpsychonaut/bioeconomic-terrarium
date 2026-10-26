"""
Modal deployment for Terrarium experiments.

Single-container approach: model + experiment run together on one A100 GPU.
No inter-container calls, no serialization bugs.

Usage:
  1. pip install modal
  2. modal token set --token-id <ID> --token-secret <SECRET>
  3. modal run terrarium/modal_run.py

Estimated cost: ~$7-8 on Modal Starter plan.
"""

import modal
import json
import sys
from pathlib import Path

app = modal.App("terrarium")

MODEL_ID = "Qwen/Qwen2.5-72B-Instruct-AWQ"
GPU = "A100-80GB"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("vllm>=0.8.0", "torch>=2.4.0", "autoawq")
    .env({"VLLM_USE_FLASHINFER": "0"})
    .add_local_dir("terrarium", remote_path="/root/terrarium")
)


@app.function(
    image=image,
    gpu=GPU,
    timeout=7200,
    scaledown_window=300,
)
def run_all_experiments():
    """Load model once, run all 4 experiments sequentially on the same GPU."""
    from vllm import LLM, SamplingParams

    sys.path.insert(0, "/root")
    from terrarium.engine.substrates.ant_colony import build_colony_config
    from terrarium.engine.simulation import run_terrarium
    from terrarium.engine.evidence import compute_evidence_ladder, analyse_death_cards
    from terrarium.engine.agent_backend import (
        parse_json_response, build_system_prompt,
        build_turn_prompt, build_death_card_prompt, build_chronicle_prompt,
    )

    print(f"[Terrarium] Loading model: {MODEL_ID}")
    llm = LLM(
        model=MODEL_ID,
        tensor_parallel_size=1,
        max_model_len=4096,
        trust_remote_code=True,
        quantization="awq",
        enforce_eager=True,
    )
    params = SamplingParams(temperature=0.7, max_tokens=1024)
    print("[Terrarium] Model loaded successfully")

    def generate(system: str, user: str) -> str:
        prompt = f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
        outputs = llm.generate([prompt], params)
        return outputs[0].outputs[0].text

    class LocalBackend:
        def __init__(self):
            self.call_count = 0
            self.total_tokens = 0

        def decide(self, agent, state_view, tick):
            system = build_system_prompt(agent)
            user = build_turn_prompt(agent, state_view, tick)
            raw = generate(system, user)
            self.call_count += 1
            return parse_json_response(raw)

        def elicit_death_card(self, agent, state_view):
            system = build_system_prompt(agent)
            user = build_death_card_prompt(agent, state_view)
            raw = generate(system, user)
            self.call_count += 1
            return parse_json_response(raw)

        def elicit_chronicle(self, agent, state_view):
            system = build_system_prompt(agent)
            user = build_chronicle_prompt(agent, state_view)
            raw = generate(system, user)
            self.call_count += 1
            return raw

    conditions = ["C1", "C2", "C3", "C4"]
    seed = 43
    results = []

    for condition in conditions:
        config = build_colony_config(
            condition=condition,
            budget_dollars=20.0,
            seed=seed,
            grid_size=8,
        )

        backend = LocalBackend()
        output_path = Path(f"/tmp/terrarium_run_{condition}_{seed}.json")

        print(f"\n[Terrarium] === Starting {condition} seed={seed} ===")
        print(f"[Terrarium] Budget: $20 ({config['budget_energy']} energy)")

        state = run_terrarium(config, backend, output_path, max_ticks=250)

        print(f"[Terrarium] {condition} complete: {len(state.alive_agents)} survivors, {state.tick} ticks, {backend.call_count} LLM calls")

        log_data = json.loads(output_path.read_text())
        evidence = compute_evidence_ladder(state, log_data.get('ticks'))
        death_analysis = analyse_death_cards(state, log_data.get('ticks', []))

        log_data['summary']['evidence'] = [e.to_dict() for e in evidence]
        log_data['summary']['death_analysis'] = death_analysis
        log_data['summary']['model'] = MODEL_ID
        log_data['summary']['api_calls'] = backend.call_count

        results.append({
            "condition": condition,
            "seed": seed,
            "ticks": state.tick,
            "survivors": len(state.alive_agents),
            "api_calls": backend.call_count,
            "log_data": log_data,
        })

    return results


@app.local_entrypoint()
def main():
    """Run all experiments and save results locally."""
    output_dir = Path("terrarium/logs")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Terrarium] Launching single-container run on Modal")
    print(f"[Terrarium] Model: {MODEL_ID} on {GPU}")
    print(f"[Terrarium] 4 conditions x 1 seed x 250 ticks")
    print()

    results = run_all_experiments.remote()

    for result in results:
        fname = f"run_{result['condition']}_{result['seed']}.json"
        fpath = output_dir / fname
        fpath.write_text(json.dumps(result['log_data'], indent=2, default=str))
        print(f"  Saved {fname}: {result['ticks']} ticks, {result['survivors']} survivors, {result['api_calls']} API calls")

    print(f"\n[Terrarium] All {len(results)} experiments complete.")
    print(f"[Terrarium] Results saved to {output_dir}/")

    total_calls = sum(r['api_calls'] for r in results)
    print(f"[Terrarium] Total LLM calls: {total_calls}")

    print("\n--- Summary ---")
    for r in results:
        ev = r['log_data'].get('summary', {}).get('evidence', [])
        top = ev[0] if ev else None
        top_str = f"top pair: composite={top.get('composite', 0):.3f}" if top else "no evidence"
        print(f"  {r['condition']} seed={r['seed']}: {r['ticks']}t, {r['survivors']} alive, {top_str}")
