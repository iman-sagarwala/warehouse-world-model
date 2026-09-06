"""ADG execution demo: small lateness absorbed as WAITING, not collision.

Two robots cross at one junction cell. A is planned to cross first, B second. Then we DELAY
A. Under the ADG, B waits for A to clear the junction (0 collisions). Under naive execution
(blindly follow routes), the delay desynchronises them and they collide at the junction.
Run: python scripts/demo_adg.py
"""
import os
import sys

sys.path.insert(0, "scripts")
from wwm_sim.adg import build_adg, simulate_adg, simulate_naive  # noqa: E402


def line(a, b):
    """Cells from a to b inclusive along a straight row/col (4-connected)."""
    (ax, ay), (bx, by) = a, b
    cells = []
    if ax == bx:
        step = 1 if by >= ay else -1
        for y in range(ay, by + step, step):
            cells.append((ax, y))
    else:
        step = 1 if bx >= ax else -1
        for x in range(ax, bx + step, step):
            cells.append((x, ay))
    return cells


def show(tag, res, routes):
    print(f"  {tag}: collisions = {res['collisions']}")
    for r in routes:
        cells = res["traj"][r]
        s = " ".join(f"{c[0]},{c[1]}" for c in cells[:16])
        print(f"    {r} (start->J->end): {s}{' ...' if len(cells) > 16 else ''}")


def main():
    J = (4, 5)                                   # the shared junction cell
    routes = {
        "A": line((1, 5), (7, 5)),               # EAST through J: reaches J at t=3
        "B": line((4, 9), (4, 2)),               # NORTH through J: reaches J at t=4 (A first)
    }
    order, pred = build_adg(routes)
    print("=" * 70)
    print("ADG built. Junction", J, "planned crossing order:", order[J],
          "\n-> dependency: B may enter J only AFTER A has left it.")
    print("=" * 70)

    print("\n1) PLANNED execution (no delay) — A crosses t=3, B t=4, both clean:")
    show("ADG  ", simulate_adg(routes, pred), routes)

    print("\n2) A hits 1 step of lateness (stalls 1 tick) -> it now reaches J the SAME tick as B:")
    delays = {"A": 2}                            # A can't move before tick 2 = one stall step
    adg = simulate_adg(routes, pred, delays)
    naive = simulate_naive(routes, delays)
    show("ADG  ", adg, routes)
    print(f"    -> B waited {adg['waits']['B']} extra step(s) for A to clear J; collisions = {adg['collisions']}")
    show("NAIVE", naive, routes)
    print(f"    -> naive ignores the ordering -> collisions = {naive['collisions']} (both land on J at once)")

    print("\nTakeaway: the ADG turned A's 1-step lateness into B WAITING 1 step (0 collisions,")
    print("no replan); naive execution turned the same lateness into a crash at the junction.")
    os.makedirs("results", exist_ok=True)


if __name__ == "__main__":
    main()
