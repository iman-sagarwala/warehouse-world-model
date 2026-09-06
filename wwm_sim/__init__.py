"""wwm_sim — OUR editable warehouse simulator.

This package began as a verbatim copy of the vendored TA-RWARE simulator
(`task-assignment-robotic-warehouse/tarware`), with `tarware` renamed to
`wwm_sim`. THIS is the copy we edit to add our own rulebook: battery, deadlines,
disturbances, and partial observability. The rollout engine will reuse the same
rule functions defined here on *believed* state.

The vendored `tarware` package is left UNTOUCHED — it stays as the FIFO
throughput baseline (§6.1 yardstick) and the source of layouts / task rates.

Env ids are registered under the `wwm_sim-*` prefix (vs. tarware's `tarware-*`),
so both can be imported side by side without collision.
"""

import itertools

import gymnasium as gym

from wwm_sim.spaces import observation_map
from wwm_sim.warehouse import RewardType

_obs_types = list(observation_map.keys())

_sizes = {
    "tiny": (1, 3),
    "small": (2, 3),
    "medium": (2, 5),
    "large": (3, 5),
    "extralarge": (4, 7),
}

_request_queues = {
    "tiny": 20,
    "small": 20,
    "medium": 20,
    "large": 40,
    "extralarge": 60,
}

_perms = itertools.product(_sizes.keys(), _obs_types, range(1,20), range(1, 10))

for size, obs_type, num_agvs, num_pickers in _perms:
    # normal tasks
    gym.register(
        id=f"wwm_sim-{size}-{num_agvs}agvs-{num_pickers}pickers-{obs_type}obs-v1",
        entry_point="wwm_sim.warehouse:Warehouse",
        kwargs={
            "column_height": 8,
            "shelf_rows": _sizes[size][0],
            "shelf_columns": _sizes[size][1],
            "num_agvs":  num_agvs,
            "num_pickers": num_pickers,
            "request_queue_size": _request_queues[size],
            "max_inactivity_steps": None,
            "max_steps": 500,
            "reward_type": RewardType.INDIVIDUAL,
            "observation_type": obs_type,
        },
    )

    # DENSE (Kiva-realistic) geometry, 2026-08-06. The default maps run 2-wide pod blocks with 2-cell
    # lanes everywhere -> 31% storage utilisation, i.e. 69% open aisle. Real robotic pod fields run at
    # ~65% with 3x6/4x6/4x7 clusters and narrow one-way lanes, because drive units travel UNDER the
    # pods and do not need human-width aisles. `column_width=4, highway_lanes=1, column_height=6`
    # reproduces a 4x6 Kiva cluster. Registered ALONGSIDE the originals so existing results stand.
    gym.register(
        id=f"wwm_sim-{size}dense-{num_agvs}agvs-{num_pickers}pickers-{obs_type}obs-v1",
        entry_point="wwm_sim.warehouse:Warehouse",
        kwargs={
            "column_height": 6,
            # column_width MUST be <= 2. Pickers travel highways only and step onto a shelf from an
            # ADJACENT aisle, so with 4-wide blocks the two interior columns touch no lane and are
            # physically unreachable: every rendezvous there failed to route, the AGV waited forever
            # holding its task, and the fleet stalled with free pickers idle. Measured: 36/36 route
            # lookups failed, rendezvous cells not even present in the picker graph.
            # 2-wide blocks with 1-cell lanes keep the realistic density (~57% storage, inside the
            # 40-60% band for in-aisle-picking systems) AND keep every shelf adjacent to an aisle.
            "column_width": 2,
            "highway_lanes": 1,
            "n_stations": 3,
            "shelf_rows": _sizes[size][0],
            "shelf_columns": _sizes[size][1],
            "num_agvs":  num_agvs,
            "num_pickers": num_pickers,
            "request_queue_size": _request_queues[size],
            "max_inactivity_steps": None,
            "max_steps": 500,
            "reward_type": RewardType.INDIVIDUAL,
            "observation_type": obs_type,
        },
    )

    # DUAL-CARRIAGEWAY variant. 2-cell lanes whose two cells run OPPOSITE directions, so opposing
    # traffic can never meet head-on -- the failure that survived the headway rule was two loaded AGVs
    # passing in opposite directions through a 1-cell corridor, which has no passing place. Wider
    # aisles cost density (33% vs 45%) but 2 m matches the documented narrow-aisle AMR figure (2.1 m).
    gym.register(
        id=f"wwm_sim-{size}dual-{num_agvs}agvs-{num_pickers}pickers-{obs_type}obs-v1",
        entry_point="wwm_sim.warehouse:Warehouse",
        kwargs={
            "column_height": 10,
            "column_width": 2,
            "highway_lanes": 2,
            "n_stations": 3,
            "shelf_rows": _sizes[size][0],
            "shelf_columns": _sizes[size][1],
            "num_agvs":  num_agvs,
            "num_pickers": num_pickers,
            "request_queue_size": _request_queues[size],
            "max_inactivity_steps": None,
            "max_steps": 500,
            "reward_type": RewardType.INDIVIDUAL,
            "observation_type": obs_type,
        },
    )

def full_registration():
    _perms = itertools.product(_sizes.keys(), _obs_types, _request_queues, range(1,20), range(1, 10),)
    for size, obs_type, num_agvs, num_pickers in _perms:
        # normal tasks with modified column height
        gym.register(
            id=f"wwm_sim-{size}-{num_agvs}agvs-{num_pickers}pickers-{obs_type}obs-v1",
            entry_point="wwm_sim.warehouse:Warehouse",
            kwargs={
                "column_height": 8,
                "shelf_rows": _sizes[size][0],
                "shelf_columns": _sizes[size][1],
                "num_agvs":  num_agvs,
                "num_pickers": num_pickers,
                "sensor_range": 1,
                "request_queue_size": _request_queues[size],
                "max_inactivity_steps": None,
                "max_steps": 500,
                "reward_type": RewardType.INDIVIDUAL,
                "observation_type": obs_type,
            },
        )
