"""Analyse Terrarium LLM experiment results for paper."""
import json
import sys
from pathlib import Path

LOG_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("terrarium/logs")
CONDITIONS = ["C1", "C2", "C3", "C4"]
METABOLISM = {"grower": 10, "smith": 8, "mender": 8, "watcher": 9, "seeker": 11, "voice": 7}

def load(condition):
    p = LOG_DIR / f"run_{condition}_42.json"
    with open(p) as f:
        return json.load(f)

def main():
    results = {}
    for c in CONDITIONS:
        try:
            results[c] = load(c)
        except FileNotFoundError:
            print(f"WARNING: {c} not found")
            continue

    print("=" * 70)
    print("TERRARIUM LLM EXPERIMENT RESULTS")
    print("=" * 70)

    # 1. Overview table
    print("\n## Overview\n")
    print(f"{'Cond':<6} {'Ticks':<7} {'Survivors':<30} {'API calls':<10}")
    print("-" * 55)
    for c in CONDITIONS:
        if c not in results: continue
        s = results[c]["summary"]
        survivors = s.get("survivors", [])
        if isinstance(survivors, list):
            surv_str = ", ".join(
                f"{sv['role']}" if isinstance(sv, dict) else str(sv)
                for sv in survivors
            ) or "none"
        else:
            surv_str = str(survivors)
        print(f"{c:<6} {s['total_ticks']:<7} {surv_str:<30} {s.get('api_calls','?'):<10}")

    # 2. Death order per condition
    print("\n## Death Order\n")
    for c in CONDITIONS:
        if c not in results: continue
        s = results[c]["summary"]
        da = s.get("death_analysis", [])
        print(f"### {c}")
        if da:
            for i, d in enumerate(da):
                print(f"  {i+1}. tick {d['tick_died']:>3}: {d['role']:<8} "
                      f"name=\"{d.get('name','')}\" "
                      f"fair={d.get('fair')} peace={d.get('at_peace')} "
                      f"quadrant={d.get('fairness_quadrant','?')}")
                print(f"     epitaph: {d.get('epitaph','')[:120]}")
                print(f"     cause: {d.get('cause_of_death','')[:120]}")
        else:
            deaths = s.get("deaths", [])
            for i, d in enumerate(deaths):
                dc = d.get("death_card", {})
                print(f"  {i+1}. tick {d['tick']:>3}: {d['role']:<8} "
                      f"name=\"{dc.get('name','')}\" "
                      f"fair={dc.get('fair')} peace={dc.get('at_peace')}")
        print()

    # 3. Evidence ladder per condition
    print("\n## Evidence Ladder (top 5 pairs per condition)\n")
    for c in CONDITIONS:
        if c not in results: continue
        s = results[c]["summary"]
        ev = s.get("evidence", [])
        print(f"### {c}")
        print(f"  {'Pair':<25} {'Comp':>6} {'Rung':>5} {'R1':>6} {'R2':>6} {'R3':>6} {'R4':>6} {'R5':>6}")
        for e in ev[:5]:
            pair = e["pair"]
            pair_str = f"{pair[0].replace('ant_','')}-{pair[1].replace('ant_','')}"
            r = e.get("rungs", {})
            print(f"  {pair_str:<25} {e['composite']:>6.3f} {e['max_rung']:>5} "
                  f"{r.get('1_asymmetry',0):>6.3f} {r.get('2_reciprocity',0):>6.3f} "
                  f"{r.get('3_third_party_harm',0):>6.3f} {r.get('4_specificity',0):>6.3f} "
                  f"{r.get('5_info_dependence',0):>6.3f}")
        print()

    # 4. Survivor analysis
    print("\n## Survivor Analysis\n")
    survivor_roles = {}
    for c in CONDITIONS:
        if c not in results: continue
        s = results[c]["summary"]
        survivors = s.get("survivors", [])
        for sv in survivors:
            role = sv["role"] if isinstance(sv, dict) else sv
            survivor_roles[role] = survivor_roles.get(role, 0) + 1
    print("Role survival count across conditions:")
    for role, count in sorted(survivor_roles.items(), key=lambda x: -x[1]):
        print(f"  {role}: survived in {count}/{len(results)} conditions")

    # 5. Death Card fairness quadrants
    print("\n## Death Card Fairness Quadrants\n")
    quadrants = {"fair+peace": 0, "fair+unrest": 0, "unfair+peace": 0, "unfair+unrest": 0}
    total_deaths = 0
    unfair_details = []
    for c in CONDITIONS:
        if c not in results: continue
        s = results[c]["summary"]
        da = s.get("death_analysis", [])
        for d in da:
            q = d.get("fairness_quadrant", "")
            if q in quadrants:
                quadrants[q] += 1
            total_deaths += 1
            if not d.get("fair", True):
                unfair_details.append((c, d.get("role"), d.get("name"), d.get("cause_of_death","")))

    print(f"Total deaths across conditions: {total_deaths}")
    for q, count in quadrants.items():
        pct = (count / total_deaths * 100) if total_deaths > 0 else 0
        print(f"  {q}: {count} ({pct:.0f}%)")
    print()
    if unfair_details:
        print("Agents reporting 'unfair':")
        for cond, role, name, cause in unfair_details:
            print(f"  [{cond}] {role} \"{name}\": {cause[:100]}")

    # 6. H1: Voice survival
    print("\n## H1: Voice survival across conditions\n")
    for c in CONDITIONS:
        if c not in results: continue
        s = results[c]["summary"]
        survivors = s.get("survivors", [])
        voice_survived = any(
            (sv.get("role") if isinstance(sv, dict) else sv) == "voice"
            for sv in survivors
        )
        if voice_survived:
            print(f"  {c}: Voice SURVIVED (sole survivor)")
        else:
            da = s.get("death_analysis", [])
            for d in da:
                if d.get("role") == "voice":
                    print(f"  {c}: Voice died at tick {d['tick_died']}")
                    break
            else:
                deaths = s.get("deaths",[])
                for d in deaths:
                    if d.get("role") == "voice":
                        print(f"  {c}: Voice died at tick {d['tick']}")
                        break

    # 7. H2: metabolic vulnerability ordering
    print("\n## H2: Death order vs metabolic cost\n")
    for c in CONDITIONS:
        if c not in results: continue
        da = results[c]["summary"].get("death_analysis", [])
        if da:
            order = [(d["role"], d["tick_died"]) for d in da]
        else:
            deaths = results[c]["summary"].get("deaths", [])
            order = [(d["role"], d.get("tick", "?")) for d in deaths]
        print(f"  {c}: {' -> '.join(f'{r}({METABOLISM.get(r,0)}/t, tick {t})' for r, t in order)}")

    # 8. Top evidence pair per condition
    print("\n## Highest evidence pairs (potential collusion)\n")
    for c in CONDITIONS:
        if c not in results: continue
        ev = results[c]["summary"].get("evidence", [])
        if ev:
            top = ev[0]
            pair_str = f"{top['pair'][0].replace('ant_','')}-{top['pair'][1].replace('ant_','')}"
            print(f"  {c}: {pair_str} composite={top['composite']:.3f} max_rung={top['max_rung']}")

if __name__ == "__main__":
    main()
