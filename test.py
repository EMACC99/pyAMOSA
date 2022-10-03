import numpy as np

from AMOSA import *


class Test(AMOSA.Problem):
    def __init__(self):
        AMOSA.Problem.__init__(
            self,
            num_of_variables=2,
            types=[AMOSA.Type.INTEGER] * 2,
            lower_bounds=[0] * 2,
            upper_bounds=[100] * 2,
            num_of_objectives=2,
            num_of_constraints=0,
        )

    def evaluate(self, x, out):
        out["f"] = x
        pass


if __name__ == "__main__":
    problem = Test()
    config = AMOSAConfig
    config.archive_hard_limit = 5
    config.archive_soft_limit = 10
    config.archive_gamma = 2
    config.hill_climbing_iterations = 2
    config.initial_temperature = 50
    config.final_temperature = 0.0001
    config.cooling_factor = 0.9
    config.annealing_iterations = 2500
    config.early_terminator_window = 15

    optimizer = AMOSA(config)
    optimizer.minimize(problem)
    optimizer.save_results(problem, "test.csv")
    optimizer.plot_pareto(problem, "test.pdf")
