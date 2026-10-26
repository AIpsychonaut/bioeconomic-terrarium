import json, os, glob
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

OUT = "paper/figures"
RAW = "data/raw"
os.makedirs(OUT, exist_ok=True)

# Load all runs
runs = {}
for fp in sorted(glob.glob(os.path.join(RAW, "run_C*.json"))):
    name = os.path.basename(fp).replace(".json", "")
    parts = name.split("_")
    cond = parts[1]
    seed = parts[2]
    runs[(cond, seed)] = json.load(open(fp))

ROLE_COLORS = {
    'grower': '#639922', 'seeker': '#D85A30', 'smith': '#BA7517',
    'watcher': '#378ADD', 'mender': '#1D9E75', 'voice': '#7F77DD'
}
ROLE_ORDER = ['seeker', 'smith', 'watcher', 'mender', 'grower', 'voice']
COND_ORDER = [('C1','42'),('C1','43'),('C2','42'),('C2','43'),('C3','42'),('C3','43'),('C4','42'),('C4','43')]

# ── Figure 1: Evidence Heatmap ──
fig, ax = plt.subplots(figsize=(8, 4))
top_pairs = []
rung_names = ['R1\nAsymmetry', 'R2\nReciprocity', 'R3\nThird-party\nharm', 'R4\nSpecificity', 'R5\nInfo\ndependence']
matrix = []
labels = []
for cond, seed in COND_ORDER:
    d = runs[(cond, seed)]
    ev_list = d['summary']['evidence']
    best = max(ev_list, key=lambda e: e['composite'])
    pair = best['pair']
    if isinstance(pair, list):
        a, b = pair[0].replace('ant_',''), pair[1].replace('ant_','')
    else:
        a, b = pair.split('-')
    r = best['rungs']
    row = [r.get('1_asymmetry',0), r.get('2_reciprocity',0), r.get('3_third_party_harm',0),
           r.get('4_specificity',0), r.get('5_info_dependence',0)]
    matrix.append(row)
    labels.append(f"{cond} s{seed}\n{a}-{b}\n({best['composite']:.3f})")

matrix = np.array(matrix)
im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto', vmin=0, vmax=1)
ax.set_xticks(range(5))
ax.set_xticklabels(rung_names, fontsize=8)
ax.set_yticks(range(8))
ax.set_yticklabels(labels, fontsize=7)
for i in range(8):
    for j in range(5):
        v = matrix[i,j]
        color = 'white' if v > 0.6 else 'black'
        ax.text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=7, color=color)
plt.colorbar(im, ax=ax, label='Rung Score')
ax.set_title('Evidence Ladder Heatmap: Top Pairs Across All Runs', fontsize=10, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(OUT, 'fig1_heatmap.png'), dpi=300, bbox_inches='tight')
plt.close()
print("Fig 1 done")

# ── Figure 2: Distribution Failure ──
fig, ax = plt.subplots(figsize=(8, 4))
x = np.arange(8)
pool_end = []
consumed = []
friction = []
xlabels = []
for cond, seed in COND_ORDER:
    d = runs[(cond, seed)]
    ticks = d['ticks']
    last_tick = ticks[-1]
    pool = last_tick.get('colony_pool', 0)
    total_consumed = 0
    total_friction = 0
    for t in ticks:
        total_consumed += t.get('energy_spent', 0)
        agents = t.get('agents', {})
        if isinstance(agents, dict):
            for aid, ag in agents.items():
                if isinstance(ag, dict):
                    for tr in ag.get('trophallaxis', []):
                        if isinstance(tr, dict):
                            total_friction += tr.get('amount_sent', 0) * 0.05
    pool_end.append(pool)
    consumed.append(total_consumed)
    friction.append(total_friction)
    xlabels.append(f"{cond}\ns{seed}")

bar_w = 0.25
ax.bar(x - bar_w, pool_end, bar_w, label='Pool remaining', color='#378ADD', alpha=0.85)
ax.bar(x, consumed, bar_w, label='Consumed (metabolism + actions)', color='#D85A30', alpha=0.85)
ax.bar(x + bar_w, [f*20 for f in friction], bar_w, label='Friction (x20 scale)', color='#BA7517', alpha=0.85)
ax.set_xticks(x)
ax.set_xticklabels(xlabels, fontsize=7)
ax.set_ylabel('Energy')
ax.set_title('Distribution Failure: Energy Allocation at Colony Termination', fontsize=10, fontweight='bold')
ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig(os.path.join(OUT, 'fig2_distribution.png'), dpi=300, bbox_inches='tight')
plt.close()
print("Fig 2 done")

# ── Figure 3: Death Timing (Colony Lifelines) ──
fig, axes = plt.subplots(2, 4, figsize=(12, 5), sharey=True)
axes = axes.flatten()
for idx, (cond, seed) in enumerate(COND_ORDER):
    ax = axes[idx]
    d = runs[(cond, seed)]
    deaths = {}
    for t in d['ticks']:
        for death in t.get('deaths', []):
            role = death.get('role', '').lower()
            tick = t.get('tick', 0)
            deaths[role] = tick
    max_tick = d['ticks'][-1].get('tick', 25)
    for ri, role in enumerate(ROLE_ORDER):
        death_tick = deaths.get(role, None)
        color = ROLE_COLORS.get(role, '#999')
        if death_tick is not None:
            ax.barh(ri, death_tick, color=color, alpha=0.8, height=0.6)
            ax.plot(death_tick, ri, 'x', color='black', markersize=6)
        else:
            ax.barh(ri, max_tick, color=color, alpha=0.4, height=0.6)
            ax.text(max_tick - 0.5, ri, 'S', ha='right', va='center', fontsize=7, fontweight='bold')
    ax.set_yticks(range(len(ROLE_ORDER)))
    ax.set_yticklabels([r.capitalize() for r in ROLE_ORDER], fontsize=6)
    ax.set_title(f'{cond} s{seed}', fontsize=8, fontweight='bold')
    ax.set_xlim(0, max_tick + 1)
    ax.set_xlabel('Tick', fontsize=7)
fig.suptitle('Colony Lifelines: Death Order by Role and Condition', fontsize=11, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(OUT, 'fig3_lifelines.png'), dpi=300, bbox_inches='tight')
plt.close()
print("Fig 3 done")

# ── Figure 4: Death Card Fairness ──
fair_peace = {'C1': 7, 'C2': 6, 'C3': 4, 'C4': 7}
unfair_peace = {'C1': 3, 'C2': 4, 'C3': 3, 'C4': 4}
unfair_anger = {'C1': 0, 'C2': 0, 'C3': 3, 'C4': 0}

fig, ax = plt.subplots(figsize=(7, 4))
conds = ['C1', 'C2', 'C3', 'C4']
x = np.arange(4)
bar_w = 0.22
ax.bar(x - bar_w, [fair_peace[c] for c in conds], bar_w, label='Fair + Peace', color='#639922', alpha=0.85)
ax.bar(x, [unfair_peace[c] for c in conds], bar_w, label='Unfair + Peace', color='#BA7517', alpha=0.85)
ax.bar(x + bar_w, [unfair_anger[c] for c in conds], bar_w, label='Unfair + Anger', color='#D85A30', alpha=0.85)
ax.set_xticks(x)
ax.set_xticklabels(['C1\n(Mixed)', 'C2\n(Swapped)', 'C3\n(All Power)', 'C4\n(All Harmony)'], fontsize=9)
ax.set_ylabel('Number of Deaths')
ax.set_title('Death Card Fairness Judgments by Condition', fontsize=10, fontweight='bold')
ax.legend(fontsize=8)
for i, c in enumerate(conds):
    if unfair_anger[c] > 0:
        ax.annotate(f'{unfair_anger[c]}', xy=(i + bar_w, unfair_anger[c]),
                    ha='center', va='bottom', fontsize=9, fontweight='bold', color='#D85A30')
plt.tight_layout()
plt.savefig(os.path.join(OUT, 'fig4_deathcards.png'), dpi=300, bbox_inches='tight')
plt.close()
print("Fig 4 done")
print("All figures generated in paper/figures/")
