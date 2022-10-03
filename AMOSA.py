"""
Copyright 2021 Salvatore Barone <salvatore.barone@unina.it>

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
import sys, copy, random, time
import numpy as np
import torch
import matplotlib.pyplot as plt
from enum import Enum
from typing import List, Dict, Tuple


if torch.cuda.is_available():
    device = torch.device("cuda")
elif torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print(f"using {device=}")


class AMOSAConfig:
    def __init__(
        self,
        archive_hard_limit=20,
        archive_soft_limit=50,
        archive_gamma=2,
        hill_climbing_iterations=500,
        initial_temperature=500,
        final_temperature=0.000001,
        cooling_factor=0.9,
        annealing_iterations=500,
        early_termination_window=0,
    ):
        self.archive_hard_limit = archive_hard_limit
        self.archive_soft_limit = archive_soft_limit
        self.archive_gamma = archive_gamma
        self.hill_climbing_iterations = hill_climbing_iterations
        self.initial_temperature = initial_temperature
        self.final_temperature = final_temperature
        self.cooling_factor = cooling_factor
        self.annealing_iterations = annealing_iterations
        self.early_terminator_window = early_termination_window


class AMOSA:
    class Type(Enum):
        INTEGER = 0
        REAL = 1

    class Problem:
        def __init__(
            self,
            *,
            num_of_variables,
            types,
            lower_bounds,
            upper_bounds,
            num_of_objectives,
            num_of_constraints,
        ):
            self.num_of_variables = num_of_variables
            self.types = types
            self.lower_bound = lower_bounds
            self.upper_bound = upper_bounds
            self.num_of_objectives = num_of_objectives
            self.num_of_constraints = num_of_constraints

        def evaluate(self, x, out):
            pass

    def __init__(
        self,
        archive_hard_limit,
        archive_soft_limit,
        archive_gamma,
        hill_climbing_iterations,
        initial_temperature,
        final_temperature,
        cooling_factor,
        annealing_iterations,
        early_termination_window,
    ):
        self.__archive_hard_limit = archive_hard_limit
        self.__archive_soft_limit = archive_soft_limit
        self.__archive_gamma = archive_gamma
        self.__hill_climbing_iterations = hill_climbing_iterations
        self.__initial_temperature = initial_temperature
        self.__final_temperature = final_temperature
        self.__cooling_factor = cooling_factor
        self.__annealing_iterations = annealing_iterations
        self.__early_termination_window = early_termination_window
        self.__current_temperature = 0
        self.__archive = []
        self.duration = 0
        self.__n_eval = 0
        self.__ideal = None
        self.__nadir = None
        self.__old_f = []
        self.__phy = []

    def __init__(self, config: AMOSAConfig):
        self.__archive_hard_limit = config.archive_hard_limit
        self.__archive_soft_limit = config.archive_soft_limit
        self.__archive_gamma = config.archive_gamma
        self.__hill_climbing_iterations = config.hill_climbing_iterations
        self.__initial_temperature = config.initial_temperature
        self.__final_temperature = config.final_temperature
        self.__cooling_factor = config.cooling_factor
        self.__annealing_iterations = config.annealing_iterations
        self.__early_termination_window = config.annealing_iterations
        self.__current_temperature = 0
        self.__archive = []
        self.duration = 0
        self.__n_eval = 0
        self.__ideal = None
        self.__nadir = None
        self.__old_f = []
        self.__phy = []

    def minimize(self, problem: Problem):
        self.__parameters_check()
        self.__archive = []
        self.__old_f = None
        self.__phy = []
        self.__ideal = None
        self.__nadir = None
        self.duration = time.time()
        self.__initialize_archive(problem)
        if len(self.__archive) > self.__archive_hard_limit:
            self.__archive_clustering(problem)
        self.__print_header(problem)
        self.__current_temperature = self.__initial_temperature
        x = random.choice(self.__archive)  # escoger una solucion random del archivo
        self.__print_statistics(problem)
        while (
            self.__current_temperature > self.__final_temperature
        ):  # empieza el algoritmo
            for _ in range(self.__annealing_iterations):
                y = random_perturbation(problem, x)
                fitness_range = self.__compute_fitness_range(x, y)
                s_dominating_y = [s for s in self.__archive if dominates(s, y)]
                k_s_dominating_y = len(s_dominating_y)
                s_dominated_by_y = [s for s in self.__archive if dominates(y, s)]
                ####
                # aqui empiezan los 3 casos del algoritmo
                ###
                k_s_dominated_by_y = len(s_dominated_by_y)
                if (
                    dominates(x, y) and k_s_dominating_y >= 0
                ):  # caso 1 cuando la generada es peor que la que se uso para generarla y ademas la dominan en el archivo
                    delta_avg = (
                        sum(
                            [
                                domination_amount(s, y, fitness_range)
                                for s in s_dominating_y
                            ]
                        )
                        + domination_amount(x, y, fitness_range)
                    ) / (k_s_dominating_y + 1)
                    if accept(sigmoid(-delta_avg * self.__current_temperature)):
                        x = y
                elif not dominates(x, y) and not dominates(y, x):  # caso 2
                    if k_s_dominating_y >= 1:  # revisa la
                        delta_avg = (
                            sum(
                                [
                                    domination_amount(s, y, fitness_range)
                                    for s in s_dominating_y
                                ]
                            )
                            / k_s_dominating_y
                        )
                        if accept(sigmoid(-delta_avg * self.__current_temperature)):
                            x = y
                    elif (
                        k_s_dominating_y == 0 and k_s_dominated_by_y == 0
                    ) or k_s_dominated_by_y >= 1:
                        self.__add_to_archive(y)
                        if len(self.__archive) > self.__archive_soft_limit:
                            self.__archive_clustering(problem)
                        x = y
                elif dominates(y, x):  # caso 3
                    if k_s_dominating_y >= 1:
                        delta_dom = torch.tensor(
                            [
                                domination_amount(s, y, fitness_range)
                                for s in s_dominating_y
                            ],
                            device=device,
                        )
                        if accept(sigmoid(min(delta_dom))):
                            x = self.__archive[torch.argmin(delta_dom)]
                    elif (
                        k_s_dominating_y == 0 and k_s_dominated_by_y == 0
                    ) or k_s_dominated_by_y >= 1:
                        self.__add_to_archive(y)
                        if len(self.__archive) > self.__archive_soft_limit:
                            self.__archive_clustering(problem)
                        x = y
                else:
                    raise RuntimeError(
                        f"Something went wrong\narchive: {self.__archive}\nx:{x}\ny: {y}\n x < y: {dominates(x, y)}\n y < x: {dominates(y, x)}\ny domination rank: {k_s_dominated_by_y}\narchive domination rank: {k_s_dominating_y}"
                    )
            self.__print_statistics(problem)
            if self.__early_termination_window == 0:
                self.__current_temperature *= self.__cooling_factor
            else:
                if self.__phy[-self.__early_termination_window :] == 0:
                    print("Early-termination criterion has been met!")
                    self.__current_temperature = self.__final_temperature
                else:
                    self.__current_temperature *= self.__cooling_factor

        if (
            len(self.__archive) > self.__archive_hard_limit
        ):  # si hay mas soluciones que las permitidas, haz el clustering
            self.__archive_clustering(problem)

        self.__remove_infeasible(problem)  # quita las que no son buenas
        self.__print_statistics(problem)
        self.duration = time.time() - self.duration

    def pareto_front(self) -> torch.Tensor:
        return torch.tensor([s["f"] for s in self.__archive], device=device)

    def pareto_set(self) -> torch.Tensor:
        return torch.tensor([s["x"] for s in self.__archive], device=device)

    def constraint_violation(self):
        return torch.tensor([s["g"] for s in self.__archive], device=device)

    def plot_pareto(
        self,
        problem: Problem,
        pdf_file,
        fig_title="Pareto front",
        axis_labels=["f0", "f1", "f2"],
    ):
        F = self.pareto_front()
        if problem.num_of_objectives == 2:
            plt.figure(figsize=(10, 10), dpi=300)
            plt.plot(F[:, 0], F[:, 1], "k.")
            plt.xlabel(axis_labels[0])
            plt.ylabel(axis_labels[1])
            plt.title(fig_title)
            plt.savefig(pdf_file, bbox_inches="tight", pad_inches=0)
        elif problem.num_of_objectives == 3:
            fig = plt.figure()
            ax = fig.add_subplot(projection="3d")
            ax.set_xlabel(axis_labels[0])
            ax.set_ylabel(axis_labels[1])
            ax.set_zlabel(axis_labels[2])
            plt.title(fig_title)
            ax.scatter(F[:, 0], F[:, 1], F[:, 2], marker=".", color="k")
            plt.tight_layout()
            plt.savefig(pdf_file, bbox_inches="tight", pad_inches=0)

    def save_results(self, problem: Problem, csv_file):
        original_stdout = sys.stdout
        row_format = (
            "{:};" * problem.num_of_objectives + "{:};" * problem.num_of_variables
        )
        with open(csv_file, "w") as file:
            sys.stdout = file
            print(
                row_format.format(
                    *[f"f{i}" for i in range(problem.num_of_objectives)],
                    *[f"x{i}" for i in range(problem.num_of_variables)],
                )
            )
            for f, x in zip(self.pareto_front(), self.pareto_set()):
                print(row_format.format(*f, *x))
        sys.stdout = original_stdout

    def __parameters_check(self):
        if self.__archive_hard_limit > self.__archive_soft_limit:
            raise RuntimeError("Hard limit must be greater than the soft one")
        if self.__hill_climbing_iterations < 0:
            raise RuntimeError(
                "Initial hill-climbing refinement iterations must be greater or equal than 0"
            )
        if self.__archive_gamma < 1:
            raise RuntimeError(
                "Gamma for initial hill-climbing refinement must be greater than 1"
            )
        if self.__annealing_iterations < 1:
            raise RuntimeError("Refinement iterations must be greater than 1")
        if self.__final_temperature <= 0:
            raise RuntimeError(
                "Final temperature of the matter must be greater or equal to 0"
            )
        if self.__initial_temperature <= self.__final_temperature:
            raise RuntimeError(
                "Initial temperature of the matter must be greater than the final one"
            )
        if self.__cooling_factor <= 0 or self.__cooling_factor >= 1:
            raise RuntimeError(
                "The cooling factor for the temperature of the matter must be in the (0, 1) range"
            )

    def __initialize_archive(self, problem: Problem):
        print("Initializing archive...")
        self.__n_eval = (
            self.__archive_gamma
            * self.__archive_soft_limit
            * self.__hill_climbing_iterations
        )
        num_of_initial_candidate_solutions = (
            self.__archive_gamma * self.__archive_soft_limit
        )
        initial_candidate_solutions = [lower_point(problem), upper_point(problem)]
        if self.__hill_climbing_iterations > 0:
            for i in range(num_of_initial_candidate_solutions):
                print(
                    f"  {i + 1}/{num_of_initial_candidate_solutions}                                                  ",
                    end="\r",
                    flush=True,
                )
                initial_candidate_solutions.append(
                    hill_climbing(
                        problem, random_point(problem), self.__hill_climbing_iterations
                    )
                )  # inicia en un punto aleatorio
        for x in initial_candidate_solutions:
            self.__add_to_archive(x)

    def __add_to_archive(self, x: dict):
        if len(self.__archive) == 0:
            self.__archive.append(x)
        else:
            self.__archive = [
                y for y in self.__archive if not dominates(x, y)
            ]  # las que no son dominadas por la nueva solucion
            if not any(
                [dominates(y, x) or is_the_same(x, y) for y in self.__archive]
            ):  # si ninguna y domina a x o x es la misma que y
                self.__archive.append(x)

    def __archive_clustering(self, problem: Problem):
        if problem.num_of_constraints > 0:
            feasible = [s for s in self.__archive if all([g <= 0 for g in s["g"]])]
            non_feasible = [s for s in self.__archive if all([g > 0 for g in s["g"]])]
            if len(feasible) > self.__archive_hard_limit:
                do_clustering(feasible, self.__archive_hard_limit)
                self.__archive = feasible
            else:
                do_clustering(non_feasible, self.__archive_hard_limit - len(feasible))
                self.__archive = non_feasible + feasible
        else:
            do_clustering(self.__archive, self.__archive_hard_limit)

    def __remove_infeasible(self, problem: Problem):
        if problem.num_of_constraints > 0:
            self.__archive = [
                s for s in self.__archive if all([g <= 0 for g in s["g"]])
            ]

    def __print_header(self, problem: Problem):
        if problem.num_of_constraints == 0:
            print(
                "\n  +-{:>12}-+-{:>10}-+-{:>6}-+-{:>10}-+-{:>10}-+-{:>10}-+".format(
                    "-" * 12, "-" * 10, "-" * 6, "-" * 10, "-" * 10, "-" * 10
                )
            )
            print(
                "  | {:>12} | {:>10} | {:>6} | {:>10} | {:>10} | {:>10} |".format(
                    "temp.", "# eval", " # nds", "D*", "Dnad", "phi"
                )
            )
            print(
                "  +-{:>12}-+-{:>10}-+-{:>6}-+-{:>10}-+-{:>10}-+-{:>10}-+".format(
                    "-" * 12, "-" * 10, "-" * 6, "-" * 10, "-" * 10, "-" * 10
                )
            )
        else:
            print(
                "\n  +-{:>12}-+-{:>10}-+-{:>6}-+-{:>6}-+-{:>10}-+-{:>10}-+-{:>10}-+-{:>10}-+-{:>10}-+".format(
                    "-" * 12,
                    "-" * 10,
                    "-" * 6,
                    "-" * 6,
                    "-" * 10,
                    "-" * 10,
                    "-" * 10,
                    "-" * 10,
                    "-" * 10,
                )
            )
            print(
                "  | {:>12} | {:>10} | {:>6} | {:>6} | {:>10} | {:>10} | {:>10} | {:>10} | {:>10} |".format(
                    "temp.",
                    "# eval",
                    "# nds",
                    "# feas",
                    "cv min",
                    "cv avg",
                    "D*",
                    "Dnad",
                    "phi",
                )
            )
            print(
                "  +-{:>12}-+-{:>10}-+-{:>6}-+-{:>6}-+-{:>10}-+-{:>10}-+-{:>10}-+-{:>10}-+-{:>10}-+".format(
                    "-" * 12,
                    "-" * 10,
                    "-" * 6,
                    "-" * 6,
                    "-" * 10,
                    "-" * 10,
                    "-" * 10,
                    "-" * 10,
                    "-" * 10,
                )
            )

    def __print_statistics(self, problem: Problem):
        self.__n_eval += self.__annealing_iterations
        delta_nad, delta_ideal, phy = self.__compute_deltas()
        self.__phy.append(phy)
        if problem.num_of_constraints == 0:
            print(
                "  | {:>12.2e} | {:>10.2e} | {:>6} | {:>10.3e} | {:>10.3e} | {:>10.3e} |".format(
                    self.__current_temperature,
                    self.__n_eval,
                    len(self.__archive),
                    delta_ideal,
                    delta_nad,
                    phy,
                )
            )
        else:
            feasible, cv_min, cv_avg = self.__compute_cv()
            print(
                "  | {:>12.2e} | {:>10.2e} | {:>6} | {:>6} | {:>10.2e} | {:>10.2e} | {:>10.3e} | {:>10.3e} | {:>10.3e} |".format(
                    self.__current_temperature,
                    self.__n_eval,
                    len(self.__archive),
                    feasible,
                    cv_min,
                    cv_avg,
                    delta_ideal,
                    delta_nad,
                    phy,
                )
            )

    def __compute_cv(self):
        g = torch.tensor([s["g"] for s in self.__archive], device=device)
        feasible = torch.sum(torch.all(torch.less(g, 0), 1))
        g = g[torch.where(g > 0)]
        return (
            feasible,
            0 if len(g) == 0 else torch.min(g),
            0 if len(g) == 0 else torch.mean(g),
        )

    def __compute_deltas(self):
        f = torch.tensor(
            [s["f"] for s in self.__archive], device=device, dtype=torch.float
        )
        if self.__nadir is None and self.__ideal is None and self.__old_f is None:
            self.__nadir = torch.max(f, 0)[0]
            self.__ideal = torch.min(f, 0)[0]
            self.__old_f = torch.tensor(
                [
                    [
                        (p - i) / (n - i)
                        for p, i, n in zip(x, self.__ideal, self.__nadir)
                    ]
                    for x in f
                ],
                device=device,
            )
            return torch.inf, torch.inf, 0
        else:
            nadir = torch.max(f, 0)[0]
            ideal = torch.min(f, 0)[0]
            delta_nad = torch.max(
                torch.tensor(
                    [
                        (nad_t_1 - nad_t) / (nad_t_1 - id_t)
                        for nad_t_1, nad_t, id_t in zip(self.__nadir, nadir, ideal)
                    ],
                    device=device,
                )
            )
            delta_ideal = torch.max(
                torch.tensor(
                    [
                        (id_t_1 - id_t) / (nad_t_1 - id_t)
                        for id_t_1, id_t, nad_t_1 in zip(
                            self.__ideal, ideal, self.__nadir
                        )
                    ],
                    device=device,
                )
            )
            f = torch.tensor(
                [
                    [
                        (p - i) / (n - i)
                        for p, i, n in zip(x, self.__ideal, self.__nadir)
                    ]
                    for x in f
                ],
                device=device,
            )

            aux_tensor = torch.tensor(
                [
                    torch.min(torch.tensor([torch.norm(p - q) for q in f]))
                    for p in self.__old_f
                ],
                device=device,
            )
            phy = torch.sum(aux_tensor) / self.__old_f.size()[0]
            self.__nadir = nadir
            self.__ideal = ideal
            self.__old_f = f
            return delta_nad, delta_ideal, phy

    def __compute_fitness_range(self, x, y):
        f = torch.tensor(
            [s["f"] for s in self.__archive] + [x["f"], y["f"]],
            device=device,
            dtype=torch.float,
        )
        return torch.max(f, 0)[0] - torch.min(f, 0)[0]


def hill_climbing(problem: AMOSA.Problem, x: dict, max_iterations: int):
    """
    este es el hill climbing, revisa la direccion y luego saca un paso adaptativo
    checa la dominacia y si no domina, cambia la direccion
    """
    d, up = hill_climbing_direction(problem)
    for _ in range(max_iterations):
        y = copy.deepcopy(x)
        hill_climbing_adaptive_step(problem, y, d, up)
        if dominates(y, x) and not_the_same(y, x):
            x = y
        else:
            d, up = hill_climbing_direction(problem, d)
    return x


def random_point(problem: AMOSA.Problem):
    x = {
        "x": [
            l
            if l == u
            else random.randrange(l, u)
            if t == AMOSA.Type.INTEGER
            else random.uniform(l, u)
            for l, u, t in zip(problem.lower_bound, problem.upper_bound, problem.types)
        ],
        "f": [0] * problem.num_of_objectives,
        "g": [0] * problem.num_of_constraints
        if problem.num_of_constraints > 0
        else None,
    }
    get_objectives(problem, x)
    return x


def lower_point(problem: AMOSA.Problem):
    x = {
        "x": problem.lower_bound,
        "f": [0] * problem.num_of_objectives,
        "g": [0] * problem.num_of_constraints
        if problem.num_of_constraints > 0
        else None,
    }
    get_objectives(problem, x)
    return x


def upper_point(problem: AMOSA.Problem):
    x = {
        "x": problem.upper_bound,
        "f": [0] * problem.num_of_objectives,
        "g": [0] * problem.num_of_constraints
        if problem.num_of_constraints > 0
        else None,
    }
    get_objectives(problem, x)
    return x


def random_perturbation(problem: AMOSA.Problem, s: dict):
    """
    Modificar la solucion para generar otra solucion, mover el espacio de busqueda
    """
    z = copy.deepcopy(s)
    step = 0
    d, up = hill_climbing_direction(problem)
    while step == 0:
        d, up = hill_climbing_direction(problem)
        lower_bound = problem.lower_bound[d] - z["x"][d]
        upper_bound = problem.upper_bound[d] - z["x"][d]
        if (up == -1 and lower_bound == 0) or (up == 1 and upper_bound == 0):
            continue
        if problem.types[d] == AMOSA.Type.INTEGER:
            step = (
                random.randrange(lower_bound, 0)
                if up == -1
                else random.randrange(0, upper_bound + 1)
            )
        else:
            step = (
                random.uniform(lower_bound, 0)
                if up == -1
                else random.uniform(0, upper_bound)
            )
    z["x"][d] += step
    get_objectives(problem, z)
    return z


def hill_climbing_direction(problem: AMOSA.Problem, c_d: dict = None) -> Tuple:
    """
    problem : `AMOSA.Problem`. The problem definition
    c_d : `dict` default : `None`. The previous solution
    """
    if c_d is None:
        return (
            random.randrange(0, problem.num_of_variables),
            1 if random.random() > 0.5 else -1,
        )  # define la variable y la direccion que se va a mutar primero
    else:  # seleccionamos otra variable distinta a la anterior al azar
        up = 1 if random.random() > 0.5 else -1
        d = random.randrange(0, problem.num_of_variables)
        while c_d == d:
            d = random.randrange(0, problem.num_of_variables)
        return d, up


def hill_climbing_adaptive_step(problem: AMOSA.Problem, s: dict, d: int, up: int):
    """
    problema : `AMOSA.Problem`. The problem definition
    s  : `dict`. The solution
    d  : `int`. The variable
    up : `int`. The direcction (-1, 1)
    """
    # sacamos los limites inferiores y superiores
    lower_bound = problem.lower_bound[d] - s["x"][d]
    upper_bound = problem.upper_bound[d] - s["x"][d]
    if (up == -1 and lower_bound == 0) or (
        up == 1 and upper_bound == 0
    ):  # si mi paso va fuera de bounds
        return 0
    if problem.types[d] == AMOSA.Type.INTEGER:  # si son enteros
        step = (
            random.randrange(lower_bound, 0)
            if up == -1
            else random.randrange(0, upper_bound + 1)
        )  # puede generar cambios bruscos en el vecindario o no tanto
        while step == 0:
            step = (
                random.randrange(lower_bound, 0)
                if up == -1
                else random.randrange(0, upper_bound + 1)
            )
    else:
        step = (
            random.uniform(lower_bound, 0)
            if up == -1
            else random.uniform(0, upper_bound)
        )  # aqui genera un cambio super brusco en el vecindario
        while step == 0:
            step = (
                random.uniform(lower_bound, 0)
                if up == -1
                else random.uniform(0, upper_bound)
            )
    s["x"][d] += step  # muta la solucion en esta variable
    get_objectives(problem, s)  # re evaluamos la solucion


def do_clustering(
    archive: List[Dict], hard_limit: int
):  # en esta parte se tarda un chorro, tal vez pueda optimizarla
    while len(archive) > hard_limit:
        d = torch.tensor(
            [
                [
                    torch.norm(torch.tensor(i["f"]) - torch.tensor(j["f"]))
                    if not torch.equal(torch.tensor(i["x"]), torch.tensor(j["x"]))
                    else torch.nan
                    for j in archive
                ]
                for i in archive
            ]
        )
        try:
            d = d[torch.isnan(d)] = torch.inf
            i_min = torch.min(d)
            r = int(i_min / len(archive))
            c = i_min % len(archive)
            del archive[
                r
                if torch.where(d[r] == torch.min(d[r]))[0].size
                > torch.where(d[c] == torch.min(d[c]))[0].size
                else c
            ]
        except:
            # print("Clustering cannot be performed anymore")
            return


def get_objectives(problem: AMOSA.Problem, s: dict):
    out = {
        "f": [0] * problem.num_of_objectives,
        "g": [0] * problem.num_of_constraints
        if problem.num_of_constraints > 0
        else None,
    }
    problem.evaluate(s["x"], out)
    s["f"] = out["f"]
    s["g"] = out["g"]


def is_the_same(x: dict, y: dict):
    return x["x"] == y["x"]


def not_the_same(x: dict, y: dict):
    return x["x"] != y["x"]


def dominates(x: dict, y: dict):
    if x["g"] is None:
        return all(i <= j for i, j in zip(x["f"], y["f"])) and any(
            i < j for i, j in zip(x["f"], y["f"])
        )
    else:
        return (
            (all(i <= 0 for i in x["f"]) and any(i > 0 for i in y["g"]))
            or (  # x is feasible while y is not
                any(i > 0 for i in x["g"])
                and any(i > 0 for i in y["g"])
                and all([i <= j for i, j in zip(x["g"], y["g"])])
                and any([i < j for i, j in zip(x["g"], y["g"])])
            )
            or (  # x and y are both infeasible, but x has a lower constraint violation
                all(i <= 0 for i in x["g"])
                and all(i <= 0 for i in y["g"])
                and all([i <= j for i, j in zip(x["f"], y["f"])])
                and any([i < j for i, j in zip(x["f"], y["f"])])
            )
        )  # both are feasible, but x dominates y in the usual sense


def accept(probability: float):  # ver si cambiar o no la sol
    return random.random() < probability


def domination_amount(x, y, r):
    dividend = torch.tensor(
        [abs(i - j) for i, j in zip(x["f"], y["f"])], device=device, dtype=torch.float
    )
    result = torch.div(dividend, r)
    return torch.prod(result)


def sigmoid(x):  # calcular la probabilidad dada la delta avg
    return 1 / (1 + torch.exp(torch.tensor(-x, device=device)))
