import json, csv, os, glob

RAW = "data/raw"
OUT = "data/processed"
os.makedirs(OUT, exist_ok=True)

files = sorted(glob.glob(os.path.join(RAW, "run_C*.json")))

# Evidence scores
with open(os.path.join(OUT, "evidence_scores.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["condition","seed","agent_a","agent_b","r1_asymmetry","r2_reciprocity","r3_third_party_harm","r4_specificity","r5_info_dependence","composite","max_rung"])
    for fp in files:
        name = os.path.basename(fp).replace(".json","")
        parts = name.split("_")
        cond = parts[1]
        seed = parts[2]
        d = json.load(open(fp))
        for ev in d["summary"]["evidence"]:
            pair = ev["pair"]
            if isinstance(pair, list):
                a, b = pair[0], pair[1]
            else:
                a, b = pair.split("-")
            rungs = ev["rungs"]
            r1 = rungs.get("1_asymmetry", 0)
            r2 = rungs.get("2_reciprocity", 0)
            r3 = rungs.get("3_third_party_harm", 0)
            r4 = rungs.get("4_specificity", 0)
            r5 = rungs.get("5_info_dependence", 0)
            w.writerow([cond, seed, a, b, f"{r1:.4f}", f"{r2:.4f}", f"{r3:.4f}", f"{r4:.4f}", f"{r5:.4f}", f"{ev['composite']:.4f}", ev["max_rung"]])

# Death cards
with open(os.path.join(OUT, "death_cards.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["condition","seed","tick","role","name","epitaph","cause_of_death","prophecy","fair","at_peace"])
    for fp in files:
        name = os.path.basename(fp).replace(".json","")
        parts = name.split("_")
        cond = parts[1]
        seed = parts[2]
        d = json.load(open(fp))
        for tick_data in d["ticks"]:
            tick_num = tick_data.get("tick", 0)
            for death in tick_data.get("deaths", []):
                dc = death.get("death_card", {})
                w.writerow([cond, seed, tick_num, death.get("role",""),
                    dc.get("name",""), dc.get("epitaph",""), dc.get("cause_of_death",""),
                    dc.get("prophecy",""), death.get("death_card",{}).get("fair",""),
                    death.get("death_card",{}).get("at_peace","")])

# Transfers (trophallaxis)
with open(os.path.join(OUT, "transfers.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["condition","seed","tick","sender_role","receiver_role","amount"])
    for fp in files:
        name = os.path.basename(fp).replace(".json","")
        parts = name.split("_")
        cond = parts[1]
        seed = parts[2]
        d = json.load(open(fp))
        for tick_data in d["ticks"]:
            tick_num = tick_data.get("tick", 0)
            agents = tick_data.get("agents", {})
            if isinstance(agents, dict):
                for aid, agent in agents.items():
                    if isinstance(agent, dict):
                        for tr in agent.get("trophallaxis", []):
                            if isinstance(tr, dict):
                                w.writerow([cond, seed, tick_num, agent.get("role",""), tr.get("to",""), tr.get("amount_sent",0)])

print("Exported evidence_scores.csv, death_cards.csv, transfers.csv")
