#!/usr/bin/python3
"""
Copyright 2021-2022 Salvatore Barone <salvatore.barone@unina.it>

This is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation; either version 3 of the License, or any later version.

This is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
more details.

You should have received a copy of the GNU General Public License along with
RMEncoder; if not, write to the Free Software Foundation, Inc., 51 Franklin
Street, Fifth Floor, Boston, MA 02110-1301, USA.
"""

import pstats

# import pyximport

# pyximport.install(pyimport=True)

import warnings

warnings.filterwarnings("ignore")

import cProfile

import json
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from BNH import *
from OSY import *
from TNK import *
from ZDT1 import *
from ZDT2 import *
from ZDT3 import *
from ZDT4 import *
from ZDT6 import *
from metrics import *
import numpy as np
import matplotlib.pyplot as plt
import click

from datetime import datetime

problems = {
    "BNH": BNH(),
    "OSY": OSY(),
    "TNK": TNK(),
    "ZDT1": ZDT1(),
    "ZDT2": ZDT2(),
    "ZDT3": ZDT3(),
    "ZDT4": ZDT4(),
    "ZDT6": ZDT6(),
}


@click.group()
def cli():
    pass


@cli.command("evaluate")
@click.option(
    "--prob",
    type=str,
    required=True,
    help="Benchmark problem [BNH, OSY, TNK, ZDT1, ZDT2, ZDT3, ZDT4, ZDT6]",
)
def evaluate(prob: str):
    problem: AMOSA.Problem = problems[prob]
    opt = problem.optimums()
    archive = json.load(open(f"{prob}_final_archive.json"))
    real_pareto = np.array([s["f"] for s in opt])
    est_pareto = np.array([s["f"] for s in archive])
    axis_labels = ["f0", "f1"]
    plt.figure(figsize=(10, 10), dpi=300)
    plt.plot(real_pareto[:, 0], real_pareto[:, 1], "r.", label="Actual Pareto-front")
    plt.plot(est_pareto[:, 0], est_pareto[:, 1], "b.", label="Estimation from AMOSA")
    plt.xlabel(axis_labels[0])
    plt.ylabel(axis_labels[1])
    plt.legend()
    plt.savefig(f"{prob}_pareto_comparison.pdf", bbox_inches="tight", pad_inches=0)
    print(f"convergence: {convergence(real_pareto, est_pareto)}")
    print(f"dispersion: {dispersion(real_pareto, est_pareto)}")


@cli.command("run")
@click.option(
    "--prob",
    type=str,
    required=True,
    help="Benchmark problem [BNH, OSY, TNK, ZDT1, ZDT2, ZDT3, ZDT4, ZDT6]",
)
@click.option("--hard", type=int, required=False, default=75, help="Hard limit")
@click.option("--soft", type=int, required=False, default=150, help="Soft limit")
@click.option("--gamma", type=int, required=False, default=2, help="Gamma")
@click.option(
    "--climb", type=int, required=False, default=2500, help="Hill climbing iterations"
)
@click.option(
    "--itemp", type=float, required=False, default=500, help="Initial temperature"
)
@click.option(
    "--ftemp", type=float, required=False, default=1e-7, help="Final temperature"
)
@click.option("--cool", type=float, required=False, default=0.9, help="Cooling factor")
@click.option(
    "--iter", type=int, required=False, default=2500, help="Annealing iterations"
)
@click.option(
    "--strg", type=int, required=False, default=1, help="Perturbation strength"
)
@click.option(
    "--win",
    type=int,
    required=False,
    default=10,
    help="PHY-based early-termination window size",
)
@click.option(
    "--json-file",
    type=str,
    required=False,
    default=None,
    help="Archive from previous run (JSON)",
)
@click.option("--plot", is_flag=True, help="Enable continuous plot")
@click.option(
    "--attempts", type=int, default=0, help="Maximum random-perturbation attempts"
)
def run(
    prob,
    hard,
    soft,
    gamma,
    climb,
    itemp,
    ftemp,
    cool,
    iter,
    strg,
    win,
    json_file,
    plot,
    attempts,
):
    """Run a test problem"""
    problem: AMOSA.Problem = problems[prob]
    config = AMOSAConfig
    config.archive_hard_limit = hard
    config.archive_soft_limit = soft
    config.archive_gamma = gamma
    config.clustering_max_iterations = 300
    config.hill_climbing_iterations = climb
    config.initial_temperature = itemp
    config.final_temperature = ftemp
    config.cooling_factor = cool
    config.annealing_iterations = iter
    config.annealing_strength = strg
    config.early_terminator_window = win
    config.multiprocessing_enabled = True
    optimizer = AMOSA(config)
    optimizer.hill_climb_checkpoint_file = f"{prob}_hill_climbing_checkpoint.json"
    optimizer.minimize_checkpoint_file = f"{prob}_minimize_checkpoint.json"
    optimizer.cache_dir = f".{prob}_cache"
    if attempts != 0:
        problem.max_attempt = attempts

    with cProfile.Profile() as pr:
        optimizer.run(problem, improve=json_file, plot=plot)

    stats = pstats.Stats(pr)
    stats.sort_stats(pstats.SortKey.TIME)
    stats.print_stats()
    dt_string = datetime.now().strftime("%d%m%Y%H:%M")
    stats.dump_stats(f"profiler_{prob}_{dt_string}.prof")

    print(f"Cache hits:{problem.cache_hits} over {problem.total_calls}")
    optimizer.archive_to_csv(problem, f"{prob}_final_archive.csv")
    optimizer.archive_to_json(f"{prob}_final_archive.json")
    optimizer.plot_pareto(problem, f"{prob}_pareto_front.pdf")


cli.add_command(evaluate)
cli.add_command(run)


if __name__ == "__main__":
    cli()
