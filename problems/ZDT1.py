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
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from AMOSA import *


class ZDT1(AMOSA.Problem):
    n_var = 30

    def __init__(self):
<<<<<<<< HEAD:ZDT1.py
        n_var = 30
        AMOSA.Problem.__init__(self, num_of_variables = n_var,
                               types = [AMOSA.Type.REAL] * n_var,
                               lower_bounds= [0]*n_var, upper_bounds= [1] * n_var,
                               num_of_objectives= 2, num_of_constraints= 0)
========

        AMOSA.Problem.__init__(self, ZDT1.n_var, [AMOSA.Type.REAL] * ZDT1.n_var, [0]*ZDT1.n_var, [1] * ZDT1.n_var, 2, 0)
>>>>>>>> 0f6e5121d8bbb93ae09650966081ab809bdccdfe:problems/ZDT1.py

    def evaluate(self, x, out):
        f = x[0]
        g = 1 + 9 * sum(x[1:]) / (self.num_of_variables - 1)
        h = 1 - np.sqrt(f / g)
        out["f"] = [f, g * h ]

<<<<<<<< HEAD:ZDT1.py

if __name__ == '__main__':
    config = AMOSAConfig
    config.archive_hard_limit = 75
    config.archive_soft_limit = 150
    config.archive_gamma = 2
    config.hill_climbing_iterations = 2500
    config.initial_temperature = 500
    config.final_temperature = 0.0000001
    config.cooling_factor = 0.9
    config.annealing_iterations = 2500
    config.early_terminator_window = 15

    problem = ZDT1()
    optimizer = AMOSA(config)
    optimizer.minimize(problem)
    optimizer.save_results(problem, "zdt1.csv")
    optimizer.plot_pareto(problem, "zdt1.pdf")
========
    def optimums(self):
        """
        Optimum:
        0 <= x_1 <= 1, x_i = 0 for each i in 2...n
        """
        pareto_set = np.linspace(0, 1, 100)
        out =   [
                    {   "x": [x] + [0] * (ZDT1.n_var-1),
                        "f": [0] * self.num_of_objectives,
                        "g": [0] * self.num_of_constraints if self.num_of_constraints > 0 else None
                    } for x in pareto_set
                 ]
        for o in out:
            self.evaluate(o["x"], o)
        return out

>>>>>>>> 0f6e5121d8bbb93ae09650966081ab809bdccdfe:problems/ZDT1.py
