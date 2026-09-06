"""WHO strands, WHEN, WHERE? For every robot that ends an m3 episode hard-dead (<=0.02):
type, death step, distance to nearest bay at death, level 50 steps earlier, mission at death,
carrying?, and whether it was en route to a charger. 144 seeds, fixed m3 arm (fast)."""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

SEEDS = list(range(1, 37))


def one(seed):
    import importlib.util
    from record_race import build
    from wwm_sim.warehouse import AgentType
    spec = importlib.util.spec_from_file_location("m3b", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "m3_battery.py"))
    m3b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m3b)
    os.environ["M3SPC"] = "1500"
    env, ctrl = build("large-8-6", seed)
    from sim_priority import MissionType
    hist = {a.id: [] for a in env.agents}
    death = {}
    for t in range(500):
        env.step(ctrl.act())
        for a in env.agents:
            lvl = ctrl.battery.level.get(a.id, 1.0)
            hist[a.id].append(lvl)
            if lvl <= 0.02 and a.id not in death:
                m = (ctrl.assigned_agvs.get(a) if a in ctrl.assigned_agvs
                     else ctrl.assigned_pickers.get(a))
                c = ctrl.battery.nearest_charger(a)
                dist = abs(c[0] - a.x) + abs(c[1] - a.y) if c else -1
                death[a.id] = dict(
                    t=t, typ="AGV" if a.type == AgentType.AGV else "PK",
                    dist=dist,
                    lvl50=round(hist[a.id][max(0, t - 50)], 3),
                    mission=m.mission_type.name if m else "NONE",
                    carrying=getattr(a, "carrying_shelf", None) is not None)
    out = []
    for aid, d in death.items():
        if ctrl.battery.level.get(aid, 1.0) <= 0.02:      # still dead at end
            out.append((seed, aid, d))
    return out


if __name__ == "__main__":
    with mp.Pool(8) as pool:
        res = pool.map(one, SEEDS)
    rows = [r for sub in res for r in sub]
    print("HARD-DEAD robots across %d seeds (m3 fixed, large-8-6): %d\n" % (len(SEEDS), len(rows)))
    for (s, aid, d) in rows:
        print("  seed %-4d %-3s id=%-3d died t=%-3d dist-to-bay=%-3d lvl(t-50)=%-6s "
              "mission=%-9s carrying=%s"
              % (s, d["typ"], aid, d["t"], d["dist"], d["lvl50"], d["mission"], d["carrying"]))
    from collections import Counter
    print("\nby type:", Counter(d["typ"] for _, _, d in rows))
    print("by mission:", Counter(d["mission"] for _, _, d in rows))
    print("died en route to charger (mission CHARGING):",
          sum(1 for _, _, d in rows if d["mission"] == "CHARGING"))
    print("median dist-to-bay:", sorted(d["dist"] for _, _, d in rows)[len(rows) // 2] if rows else "-")
