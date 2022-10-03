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



class BNH(AMOSA.Problem):
    n_var = 2

    def __init__(self):
<<<<<<<< HEAD:BNH.py
        AMOSA.Problem.__init__(self, num_of_variables= 2,
                               types = [AMOSA.Type.REAL] * 2,
                               lower_bounds= [0]*2, upper_bounds= [5, 3],
                               num_of_objectives= 2, num_of_constraints= 2)
========
        AMOSA.Problem.__init__(self, BNH.n_var, [AMOSA.Type.REAL] * BNH.n_var, [0] * BNH.n_var, [5, 3], 2, 2)
>>>>>>>> 0f6e5121d8bbb93ae09650966081ab809bdccdfe:problems/BNH.py

    def evaluate(self, x, out):
        f1 = 4 * x[0] ** 2 + 4 * x[1] ** 2
        f2 = (x[0] - 5) ** 2 + (x[1] - 5) ** 2
        g1 = (x[0] - 5) ** 2 + x[1] ** 2 - 25
        g2 = 7.7 - (x[0] - 5) ** 2 - (x[1] + 3) ** 2
        out["f"] = [f1, f2 ]
        out["g"] = [g1, g2]

    def optimums(self):
        pareto_set = np.linspace(0, 3, 100)
        out = [{    "x": [x, x],
                    "f": [0] * self.num_of_objectives,
                    "g": [0] * self.num_of_constraints if self.num_of_constraints > 0 else None} for x in pareto_set ]
        pareto_set = np.linspace(3, 5, 100)
        out = out + [{  "x": [x, 3],
                        "f": [0] * self.num_of_objectives,
                        "g": [0] * self.num_of_constraints if self.num_of_constraints > 0 else None} for x in pareto_set ]
        for o in out:
            self.evaluate(o["x"], o)
        return out
