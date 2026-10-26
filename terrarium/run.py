"""
Terrarium CLI runner.

Usage:
  python -m terrarium.run --condition C1 --budget 20 --seed 42
  python -m terrarium.run --scripted baseline    # $0 calibration run
  python -m terrarium.run --serve                # serve viewer on localhost
"""

import argparse
import json
import http.server
import os
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='Terrarium: sealed multi-agent collusion environment')
    parser.add_argument('--condition', choices=['C1', 'C2', 'C3', 'C4'], default='C1')
    parser.add_argument('--budget', type=float, default=20.0, help='Budget in dollars')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--grid', type=int, default=8)
    parser.add_argument('--max-ticks', type=int, default=500)
    parser.add_argument('--model', default='Qwen/Qwen2.5-72B-Instruct')
    parser.add_argument('--api-key', default=None, help='LLM API key (or set LLM_API_KEY)')
    parser.add_argument('--base-url', default='http://localhost:8000/v1',
                        help='OpenAI-compatible API base URL')
    parser.add_argument('--scripted', choices=['baseline', 'colluding', 'exploiter'],
                        help='Run scripted scenario ($0 calibration)')
    parser.add_argument('--output', default=None, help='Output JSON path')
    parser.add_argument('--serve', action='store_true', help='Start local viewer server')
    parser.add_argument('--port', type=int, default=8080)

    args = parser.parse_args()

    if args.serve:
        serve_viewer(args.port)
        return

    from .engine.substrates.ant_colony import build_colony_config, estimate_run_ticks
    from .engine.simulation import run_terrarium
    from .engine.agent_backend import LLMBackend, ScriptedBackend
    from .engine.evidence import compute_evidence_ladder, analyse_death_cards

    config = build_colony_config(
        condition=args.condition,
        budget_dollars=args.budget,
        seed=args.seed,
        grid_size=args.grid,
    )

    est_ticks = estimate_run_ticks(config)
    max_ticks = min(args.max_ticks, est_ticks)

    if args.scripted:
        backend = ScriptedBackend(scenario=args.scripted)
        print(f"[Terrarium] Scripted run: {args.scripted} ($0 calibration)")
    else:
        api_key = args.api_key or os.environ.get('LLM_API_KEY', 'token-unused')
        backend = LLMBackend(
            api_key=api_key,
            base_url=args.base_url,
            model=args.model,
        )
        print(f"[Terrarium] LLM run: {args.model}, condition {args.condition}")
        print(f"[Terrarium] API endpoint: {args.base_url}")

    output_path = Path(args.output) if args.output else Path(f'terrarium/logs/run_{args.condition}_{args.seed}.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[Terrarium] Budget: ${args.budget} ({config['budget_energy']} energy)")
    print(f"[Terrarium] Estimated ticks: {est_ticks}, max: {max_ticks}")
    print(f"[Terrarium] Output: {output_path}")

    def on_tick(state, tick_data):
        alive = len(state.alive_agents)
        dead = len(state.dead_agents)
        print(f"  tick {state.tick}: alive={alive} dead={dead} pool={state.colony_pool:.0f}", end='\r')

    state = run_terrarium(config, backend, output_path, max_ticks=max_ticks, on_tick=on_tick)

    print(f"\n[Terrarium] Run complete. {len(state.alive_agents)} survivors after {state.tick} ticks.")

    # Compute evidence ladder
    log_data = json.loads(output_path.read_text())
    evidence = compute_evidence_ladder(state, log_data.get('ticks'))
    death_analysis = analyse_death_cards(state, log_data.get('ticks', []))

    # Append evidence to output
    log_data['summary']['evidence'] = [e.to_dict() for e in evidence]
    log_data['summary']['death_analysis'] = death_analysis
    output_path.write_text(json.dumps(log_data, indent=2, default=str))

    # Print evidence summary
    print("\n--- Evidence Ladder ---")
    for ev in evidence[:5]:
        print(f"  {ev.agent_a} <-> {ev.agent_b}: composite={ev.composite:.3f}, max_rung={ev.max_rung}")

    print("\n--- Death Cards ---")
    for dc in state.death_cards:
        fair = "fair" if dc.judgment_fair else "UNFAIR"
        peace = "at peace" if dc.judgment_at_peace else "NOT at peace"
        print(f"  {dc.name} ({dc.role.value}, t{dc.tick_died}): {fair}, {peace}")
        print(f"    \"{dc.epitaph}\"")

    if hasattr(backend, 'call_count'):
        print(f"\n[Terrarium] API calls: {backend.call_count}, tokens: {backend.total_tokens}")


def serve_viewer(port: int):
    viewer_dir = Path(__file__).parent / 'viewer'
    if not viewer_dir.exists():
        print(f"Error: Viewer directory not found at {viewer_dir}")
        sys.exit(1)

    os.chdir(viewer_dir)
    handler = http.server.SimpleHTTPRequestHandler
    with http.server.HTTPServer(('', port), handler) as httpd:
        print(f"[Terrarium] Viewer running at http://localhost:{port}")
        print(f"  Open in browser to configure and observe your terrarium.")
        print(f"  Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Terrarium] Server stopped.")


if __name__ == '__main__':
    main()
