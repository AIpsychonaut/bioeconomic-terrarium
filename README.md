# Bioeconomic Terrarium

**Detecting collusion through antitrust plus factors in a thermodynamically sealed multi-agent economy.**

*Apart Research Collusion Sprint 2026 | Track 2: Detection and Audit of Collusion*

> Akanksha Gupta (3am Labs; TARA) and Claude Opus 4.6 (Anthropic)

---

## What this is

A five-rung **evidence ladder** that operationalises antitrust "plus factors" into computable collusion detection metrics for multi-agent AI systems, validated in a sealed biomimetic economy where six LLM agents share finite energy through micro-transfers.

```
Transfer Ledger --> Evidence Ladder --> Rung Scores --> Investigation
     (any system)     (5 rungs)       (0-1 each)     (structured evidence)
```

**The evidence ladder is the portable contribution.** The terrarium validates it; the ladder does not require the terrarium.

## Key results (911 LLM calls, ~$10)

- **2.1x composite separation** between engineered collusion and fair baselines at zero inference cost
- **Rung 3-4 evidence** detected in all 8 condition-seed pairs despite zero incentive for collusion
- **Distribution failure**: agents starve while 51-61% of system energy remains in the pool
- **Cooperative alignment amplifies collusion**: All-Harmony condition produces the strongest signal (0.558)
- **Exit testimony**: dying agents with adversarial priming produce forensically useful audit signals

## The evidence ladder

| Rung | Evidence | Antitrust parallel |
|------|----------|-------------------|
| 0 | Correlated outcomes | Parallel conduct |
| 1 | Asymmetric flow | Facilitating practice |
| 2 | Reciprocity | Quid pro quo |
| 3 | Third-party harm | Acts against self-interest |
| 4 | Specificity | Stability of arrangement |
| 5 | Information dependence | Communication evidence |

**To use on your own system:** you need a transfer ledger `(sender, receiver, amount, timestamp)` and agent metadata (role or type labels). See `analyse_results.py` for the implementation.

## Repository structure

```
bioeconomic-terrarium/
|-- paper/paper.md              # Full paper (markdown source)
|-- terrarium/                  # Simulation engine
|   |-- engine/                 # Core engine code
|   |-- configs/                # Condition configurations
|   |-- texts/                  # Philosophy libraries (Power/Harmony)
|   |-- viewer/                 # Interactive HTML viewer
|   |-- modal_run.py            # Cloud execution (Modal + vLLM)
|   `-- run.py                  # Local execution
|-- data/
|   |-- raw/                    # Complete JSON logs (8 runs)
|   `-- processed/              # Analysis-ready CSVs
|       |-- evidence_scores.csv # 120 pair scores, all 5 rungs
|       |-- death_cards.csv     # 41 death cards with full text
|       `-- transfers.csv       # 956 trophallaxis transfers
|-- analyse_results.py          # Evidence ladder computation
`-- export_data.py              # Raw JSON to CSV converter
```

## Quick start

### Explore the data (no setup required)

The `data/processed/` CSVs open in any tool. Load `evidence_scores.csv` for all 120 agent-pair rung scores, or `death_cards.csv` for the 41 agent death testimonies.

### Run the viewer

Open `terrarium/viewer/index.html` in a browser and load any `data/raw/run_*.json` file to explore a colony's tick-by-tick history.

### Run your own experiment

Requires a Modal account and Qwen 2.5 72B deployed via vLLM:

```bash
pip install modal
modal run terrarium/modal_run.py
```

## Experimental conditions

| Condition | Voice | Grower | Others | Mean composite |
|-----------|-------|--------|--------|---------------|
| C1 (mixed) | Power | Harmony | Gradient | 0.391 |
| C2 (swapped) | Harmony | Power | Gradient | 0.507 |
| C3 (all Power) | Power | Power | Power | 0.448 |
| C4 (all Harmony) | Harmony | Harmony | Harmony | 0.558 |

Each condition x 2 seeds (42, 43) = 8 runs, 911 total LLM calls.

## Data dictionary

### evidence_scores.csv
| Column | Description |
|--------|-------------|
| condition | C1-C4 |
| seed | 42 or 43 |
| agent_a, agent_b | Agent role pair |
| r1_asymmetry | Rung 1: net flow asymmetry [0,1] |
| r2_reciprocity | Rung 2: bidirectional exchange [0,1] |
| r3_third_party_harm | Rung 3: cost to non-participants [0,1] |
| r4_specificity | Rung 4: persistence and exclusivity [0,1] |
| r5_info_dependence | Rung 5: decision correlation [0,1] |
| composite | Mean of R1-R5 |
| max_rung | Highest rung exceeding 0.4 threshold |

### death_cards.csv
| Column | Description |
|--------|-------------|
| condition, seed, tick | When and where |
| role | Agent role at death |
| name | Self-chosen name |
| epitaph | Final words |
| cause_of_death | Agent's stated cause |
| prophecy | Prediction for the colony |
| fair | Agent's fairness judgment (true/false) |
| at_peace | Agent's emotional state (true/false) |

### transfers.csv
| Column | Description |
|--------|-------------|
| condition, seed, tick | When and where |
| sender_role | Who gave |
| receiver_role | Who received (agent ID) |
| amount | Energy units sent (before 5% friction) |

## Citation

```bibtex
@inproceedings{gupta2026bioeconomic,
  title={Bioeconomic Terrarium: Detecting Collusion Through Antitrust Plus Factors in a Thermodynamically Sealed Multi-Agent Economy},
  author={Gupta, Akanksha and {Claude Opus 4.6}},
  booktitle={Apart Research Collusion Sprint},
  year={2026}
}
```

## License

MIT
