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
import sys, copy, random, time, os, json, warnings, math
import numpy as np
import matplotlib.pyplot as plt
from enum import Enum
from multiprocessing import cpu_count, Pool
from distutils.dir_util import mkpath
from itertools import islice


class MultiFileCacheHandle:

	def __init__(self, directory, max_size_mb=10):
		self.directory = directory
		self.max_size_mb = max_size_mb

	def read(self):
		cache = {}
		if os.path.isdir(self.directory):
			for f in os.listdir(self.directory):
				if f.endswith('.json'):
					with open(f"{self.directory}/{f}") as j:
						tmp = json.load(j)
						cache = {**cache, **tmp}
		print(f"{len(cache)} cache entries loaded from {self.directory}")
		return cache

	def write(self, cache):
		if os.path.isdir(self.directory):
			for file in os.listdir(self.directory):
				if file.endswith('.json'):
					os.remove(f"{self.directory}/{file}")
		else:
			mkpath(self.directory)
		total_entries = len(cache)
		total_size = sys.getsizeof(json.dumps(cache))
		avg_entry_size = math.ceil(total_size / total_entries)
		max_entries_per_file = int(self.max_size_mb * (2 ** 20) / avg_entry_size)
		splits = int(math.ceil(total_entries / max_entries_per_file))
		for item, count in zip(MultiFileCacheHandle.chunks(cache, max_entries_per_file), range(splits)):
			with open(f"{self.directory}/{count:09d}.json", 'w') as outfile:
				outfile.write(json.dumps(item))

	@staticmethod
	def chunks(data, max_entries):
		it = iter(data)
		for i in range(0, len(data), max_entries):
			yield {k: data[k] for k in islice(it, max_entries)}

class AMOSAConfig:
	def __init__(
			self,
			archive_hard_limit = 20,
			archive_soft_limit = 50,
			archive_gamma = 2,
			clustering_max_iterations = 300,
			hill_climbing_iterations = 500,
			initial_temperature = 500,
			final_temperature = 0.000001,
			cooling_factor = 0.9,
			annealing_iterations = 500,
			annealing_strength = 1,
			early_termination_window = 0,
			multiprocessing_enabled = True
	):
		assert archive_soft_limit >= archive_hard_limit > 0, f"soft limit: {archive_soft_limit}, hard limit: {archive_hard_limit}"
		assert archive_gamma > 0, f"gamma: {archive_gamma}"
		assert clustering_max_iterations > 0, f"clustering iterations: {clustering_max_iterations}"
		assert hill_climbing_iterations >= 0, f"hill-climbing iterations: {hill_climbing_iterations}"
		assert initial_temperature > final_temperature > 0, f"initial temperature: {initial_temperature}, final temperature: {final_temperature}"
		assert 0 < cooling_factor < 1, f"cooling factor: {cooling_factor}"
		assert annealing_iterations > 0, f"annealing iterations: {annealing_strength}"
		assert annealing_strength >= 1, f"annealing strength: {annealing_strength}"
		assert early_termination_window >= 0, f"early-termination window: {early_termination_window}"
		self.archive_hard_limit = archive_hard_limit
		self.archive_soft_limit = archive_soft_limit
		self.clustering_max_iterations = clustering_max_iterations
		self.archive_gamma = archive_gamma
		self.hill_climbing_iterations = hill_climbing_iterations
		self.initial_temperature = initial_temperature
		self.final_temperature = final_temperature
		self.cooling_factor = cooling_factor
		self.annealing_iterations = annealing_iterations
		self.annealing_strength = annealing_strength
		self.early_terminator_window = early_termination_window
		self.multiprocessing_enabled = multiprocessing_enabled


class AMOSA:
	hill_climb_checkpoint_file = "hill_climb_checkpoint.json"
	minimize_checkpoint_file = "minimize_checkpoint.json"
	cache_dir = ".cache"

	class Type(Enum):
		INTEGER = 0
		REAL = 1

	class Problem:
		def __init__(self, num_of_variables, types, lower_bounds, upper_bounds, num_of_objectives, num_of_constraints):
			assert num_of_variables == len(types), "Mismatch in the specified number of variables and their type declaration"
			assert num_of_variables == len(lower_bounds), "Mismatch in the specified number of variables and their lower bound declaration"
			assert num_of_variables == len(upper_bounds), "Mismatch in the specified number of variables and their upper bound declaration"
			self.num_of_variables = num_of_variables
			self.num_of_objectives = num_of_objectives
			self.num_of_constraints = num_of_constraints
			for t in types:
				assert t == AMOSA.Type.INTEGER or t == AMOSA.Type.REAL, "Only AMOSA.Type.INTEGER or AMOSA.Type.REAL data-types for decison variables are supported!"
			self.types = types
			for lb, ub, t in zip(lower_bounds, upper_bounds, self.types):
				assert isinstance(lb, int if t == AMOSA.Type.INTEGER else float), f"Type mismatch. Value {lb} in lower_bound is not suitable for {t}"
				assert isinstance(ub, int if t == AMOSA.Type.INTEGER else float), f"Type mismatch. Value {ub} in upper_bound is not suitable for {t}"
			self.lower_bound = lower_bounds
			self.upper_bound = upper_bounds
			self.cache = {}
			self.total_calls = 0
			self.cache_hits = 0
			self.max_attempt = self.num_of_variables

		def evaluate(self, x, out):
			pass

		def optimums(self):
			return []

		@staticmethod
		def get_cache_key(s):
			return ''.join([str(i) for i in s["x"]])

		def is_cached(self, s):
			return True if self.get_cache_key(s) in self.cache.keys() else False

		def add_to_cache(self, s):
			self.cache[self.get_cache_key(s)] = {"f": s["f"], "g": s["g"]}

		def load_cache(self, directory):
			handler = MultiFileCacheHandle(directory)
			self.cache = handler.read()

		def store_cache(self, directory):
			handler = MultiFileCacheHandle(directory)
			handler.write(self.cache)

		def archive_to_cache(self, archive):
			for s in archive:
				if not self.is_cached(s):
					self.add_to_cache(s)

	@staticmethod
	def is_the_same(x, y):
		return x["x"] == y["x"]

	@staticmethod
	def not_the_same(x, y):
		return x["x"] != y["x"]

	@staticmethod
	def get_objectives(problem, s):
		for i, t in zip(s["x"], problem.types):
			assert isinstance(i, int if t == AMOSA.Type.INTEGER else float), f"Type mismatch. This decision variable is {t}, but the internal type is {type(i)}. Please repurt this bug"
		problem.total_calls += 1
		# if s["x"] is in the cache, do not call problem.evaluate, but return the cached-entry
		if problem.is_cached(s):
			s["f"] = problem.cache[problem.get_cache_key(s)]["f"]
			s["g"] = problem.cache[problem.get_cache_key(s)]["g"]
			problem.cache_hits += 1
		else:
			# if s["x"] is not in the cache, call "evaluate" and add s["x"] to the cache
			out = {"f": [0] * problem.num_of_objectives, "g": [0] * problem.num_of_constraints if problem.num_of_constraints > 0 else None}
			problem.evaluate(s["x"], out)
			s["f"] = out["f"]
			s["g"] = out["g"]
			problem.add_to_cache(s)

	@staticmethod
	def dominates(x, y):
		if x["g"] is None:
			return all(i <= j for i, j in zip(x["f"], y["f"])) and any(i < j for i, j in zip(x["f"], y["f"]))
		else:
			return AMOSA.x_is_feasible_while_y_is_nor(x, y) or AMOSA.both_infeasible_but_x_is_better(x, y) or AMOSA.both_feasible_but_x_is_better(x, y)

	@staticmethod
	def x_is_feasible_while_y_is_nor(x, y):
		return all(i <= 0 for i in x["f"]) and any(i > 0 for i in y["g"])

	@staticmethod
	def both_infeasible_but_x_is_better(x, y):
		return any(i > 0 for i in x["g"]) and any(i > 0 for i in y["g"]) and all([i <= j for i, j in zip(x["g"], y["g"])]) and any([i < j for i, j in zip(x["g"], y["g"])])

	@staticmethod
	def both_feasible_but_x_is_better(x, y):
		return all(i <= 0 for i in x["g"]) and all(i <= 0 for i in y["g"]) and all([i <= j for i, j in zip(x["f"], y["f"])]) and any([i < j for i, j in zip(x["f"], y["f"])])

	@staticmethod
	def lower_point(problem):
		x = {"x": problem.lower_bound, "f": [0] * problem.num_of_objectives, "g": [0] * problem.num_of_constraints if problem.num_of_constraints > 0 else None}
		AMOSA.get_objectives(problem, x)
		return x

	@staticmethod
	def upper_point(problem):
		x = {"x": problem.upper_bound, "f": [0] * problem.num_of_objectives, "g": [0] * problem.num_of_constraints if problem.num_of_constraints > 0 else None}
		AMOSA.get_objectives(problem, x)
		return x

	@staticmethod
	def random_point(problem):
		x = {"x": [lb if lb == ub else random.randrange(lb, ub) if tp == AMOSA.Type.INTEGER else random.uniform(lb, ub) for lb, ub, tp in zip(problem.lower_bound, problem.upper_bound, problem.types)], "f": [0] * problem.num_of_objectives, "g": [0] * problem.num_of_constraints if problem.num_of_constraints > 0 else None}
		AMOSA.get_objectives(problem, x)
		return x

	@staticmethod
	def random_perturbation(problem, s, strength):
		z = copy.deepcopy(s)
		# while z["x"] is in the cache, repeat the random perturbation
		# a safety-exit prevents infinite loop, using a counter variable
		safety_exit = problem.max_attempt
		while safety_exit >= 0 and problem.is_cached(z):
			safety_exit -= 1
			indexes = random.sample(range(problem.num_of_variables), random.randrange(1, 1 + min([strength, problem.num_of_variables])))
			for i in indexes:
				lb = problem.lower_bound[i]
				ub = problem.upper_bound[i]
				tp = problem.types[i]
				z["x"][i] = lb if lb == ub else random.randrange(lb, ub) if tp == AMOSA.Type.INTEGER else random.uniform(lb, ub)
		AMOSA.get_objectives(problem, z)
		return z

	@staticmethod
	def accept(probability):
		return random.random() < probability

	@staticmethod
	def sigmoid(x):
		return 1 / (1 + np.exp(np.array(-x, dtype = np.float128)))

	@staticmethod
	def domination_amount(x, y, r):
		return np.prod([abs(i - j) / k for i, j, k in zip(x["f"], y["f"], r)])

	@staticmethod
	def compute_fitness_range(archive, current_point, new_point):
		f = [s["f"] for s in archive] + [current_point["f"], new_point["f"]]
		return np.nanmax(f, axis = 0) - np.nanmin(f, axis = 0)

	@staticmethod
	def hill_climbing(problem, x, max_iterations):
		d, up = AMOSA.hill_climbing_direction(problem)
		for _ in range(max_iterations):
			y = copy.deepcopy(x)
			AMOSA.hill_climbing_adaptive_step(problem, y, d, up)
			if AMOSA.dominates(y, x) and AMOSA.not_the_same(y, x):
				x = y
			else:
				d, up = AMOSA.hill_climbing_direction(problem, d)
		return x

	@staticmethod
	def hill_climbing_direction(problem, c_d = None):
		if c_d is None:
			return random.randrange(0, problem.num_of_variables), 1 if random.random() > 0.5 else -1
		else:
			up = 1 if random.random() > 0.5 else -1
			d = random.randrange(0, problem.num_of_variables)
			while c_d == d:
				d = random.randrange(0, problem.num_of_variables)
			return d, up

	@staticmethod
	def hill_climbing_adaptive_step(problem, s, d, up):
		# while z["x"] is in the cache, repeat the random perturbation
		# a safety-exit prevents infinite loop, using a counter variable
		safety_exit = problem.max_attempt
		while safety_exit >= 0 and problem.is_cached(s):
			safety_exit -= 1
			lower_bound = problem.lower_bound[d] - s["x"][d]
			upper_bound = problem.upper_bound[d] - s["x"][d]
			if (up == -1 and lower_bound == 0) or (up == 1 and upper_bound == 0):
				return 0
			if problem.types[d] == AMOSA.Type.INTEGER:
				step = random.randrange(lower_bound, 0) if up == -1 else random.randrange(0, upper_bound + 1)
				while step == 0:
					step = random.randrange(lower_bound, 0) if up == -1 else random.randrange(0, upper_bound + 1)
			else:
				step = random.uniform(lower_bound, 0) if up == -1 else random.uniform(0, upper_bound)
				while step == 0:
					step = random.uniform(lower_bound, 0) if up == -1 else random.uniform(0, upper_bound)
			s["x"][d] += step
		AMOSA.get_objectives(problem, s)

	@staticmethod
	def add_to_archive(archive, x):
		if len(archive) == 0:
			archive.append(x)
		else:
			for y in archive:
				if AMOSA.dominates(x, y):
					archive.remove(y)
			if not any([AMOSA.dominates(y, x) or AMOSA.is_the_same(x, y) for y in archive]):
				archive.append(x)

	@staticmethod
	def nondominated_merge(archives):
		nondominated_archive = []
		AMOSA.print_progressbar(0, len(archives), message = "Merging archives:")
		for i, archive in enumerate(archives):
			for x in archive:
				AMOSA.add_to_archive(nondominated_archive, x)
			AMOSA.print_progressbar(i+1, len(archives), message = "Merging archives:")
		return nondominated_archive

	@staticmethod
	def compute_cv(archive):
		g = np.array([s["g"] for s in archive])
		feasible = np.all(np.less(g, 0), axis = 1).sum()
		g = g[np.where(g > 0)]
		return feasible, 0 if len(g) == 0 else np.nanmin(g), 0 if len(g) == 0 else np.average(g)

	@staticmethod
	def remove_infeasible(problem, archive):
		if problem.num_of_constraints > 0:
			return [s for s in archive if all([g <= 0 for g in s["g"]])]
		return archive

	@staticmethod
	def remove_dominated(archive):
		nondominated_archive = []
		for x in archive:
			AMOSA.add_to_archive(nondominated_archive, x)
		return nondominated_archive

	@staticmethod
	def clustering(archive, problem, hard_limit, max_iterations, print_allowed):
		if problem.num_of_constraints > 0:
			feasible = [s for s in archive if all([g <= 0 for g in s["g"]])]
			unfeasible = [s for s in archive if any([g > 0 for g in s["g"]])]
			if len(feasible) > hard_limit:
				return AMOSA.kmeans_clustering(feasible, hard_limit, max_iterations, print_allowed)
			elif len(feasible) < hard_limit and len(unfeasible) != 0:
				return feasible + AMOSA.kmeans_clustering(unfeasible, hard_limit - len(feasible), max_iterations, print_allowed)
			else:
				return feasible
		else:
			return AMOSA.kmeans_clustering(archive, hard_limit, max_iterations, print_allowed)

	@staticmethod
	def centroid_of_set(input_set):
		d = np.array([np.nansum([np.linalg.norm(np.array(i["f"]) - np.array(j["f"])) if not np.array_equal(np.array(i["x"]), np.array(j["x"])) else np.nan for j in input_set]) for i in input_set])
		return input_set[np.nanargmin(d)]

	@staticmethod
	def kmeans_clustering(archive, num_of_clusters, max_iterations, print_allowed):
		assert max_iterations > 0
		if 1 < num_of_clusters < len(archive):
			# Initialize the centroids, using the "k-means++" method, where a random datapoint is selected as the first,
			# then the rest are initialized w/ probabilities proportional to their distances to the first
			# Pick a random point from train data for first centroid
			centroids = [random.choice(archive)]
			if print_allowed:
				AMOSA.print_progressbar(1, num_of_clusters, message = "Clustering (centroids):")
			for n in range(num_of_clusters - 1):
				# Calculate normalized distances from points to the centroids
				dists = np.array([np.nansum([np.linalg.norm(np.array(centroid["f"]) - np.array(p["f"])) for centroid in centroids]) for p in archive])
				try:
					normalized_dists = dists / np.nansum(dists)
					# Choose remaining points based on their distances
					new_centroid_idx = np.random.choice(range(len(archive)), size = 1, p = normalized_dists)[0]  # Indexed @ zero to get val, not array of val
					centroids += [archive[new_centroid_idx]]
				except (RuntimeWarning, RuntimeError, FloatingPointError) as e:
					print(e)
					print(f"Archive: {archive}")
					print(f"Centroids: {centroids}")
					print(f"Distance: {dists}")
					print(f"Normalized distance: {dists / np.nansum(dists)}")
					exit()
				if print_allowed:
					AMOSA.print_progressbar(n, num_of_clusters, message = "Clustering (centroids):")
			# Iterate, adjusting centroids until converged or until passed max_iter
			if print_allowed:
				AMOSA.print_progressbar(0, max_iterations, message = "Clustering (kmeans):")
			for n in range(max_iterations):
				# Sort each datapoint, assigning to nearest centroid
				sorted_points = [[] for _ in range(num_of_clusters)]
				for x in archive:
					dists = [np.linalg.norm(np.array(x["f"]) - np.array(centroid["f"])) for centroid in centroids]
					centroid_idx = np.argmin(dists)
					sorted_points[centroid_idx].append(x)
				# Push current centroids to previous, reassign centroids as mean of the points belonging to them
				prev_centroids = centroids
				centroids = [AMOSA.centroid_of_set(cluster) if len(cluster) != 0 else centroid for cluster, centroid in zip(sorted_points, prev_centroids)]
				if print_allowed:
					AMOSA.print_progressbar(n, max_iterations, message = "Clustering (kmeans):")
				if np.array_equal(centroids, prev_centroids) and print_allowed:
					AMOSA.print_progressbar(max_iterations, max_iterations, message = "Clustering (kmeans):")
					break
			print("", end = "\r", flush = True)
			return centroids
		elif num_of_clusters == 1:
			return [AMOSA.centroid_of_set(archive)]
		else:
			return archive

	@staticmethod
	def inverted_generational_distance(p_t, p_tau):
		return np.nansum([np.nanmin([np.linalg.norm(p - q) for q in p_t[:]]) for p in p_tau[:]]) / len(p_tau)

	def __init__(self, config):
		warnings.filterwarnings("error")
		self.__archive_hard_limit = config.archive_hard_limit
		self.__archive_soft_limit = config.archive_soft_limit
		self.__archive_gamma = config.archive_gamma
		self.__clustering_max_iterations = config.clustering_max_iterations
		self.__hill_climbing_iterations = config.hill_climbing_iterations
		self.__initial_temperature = config.initial_temperature
		self.__final_temperature = config.final_temperature
		self.__cooling_factor = config.cooling_factor
		self.__annealing_iterations = config.annealing_iterations
		self.__annealing_strength = config.annealing_strength
		self.__early_termination_window = config.early_terminator_window
		self.__multiprocessing_enables = config.multiprocessing_enabled
		self.hill_climb_checkpoint_file = "hill_climb_checkpoint.json"
		self.minimize_checkpoint_file = "minimize_checkpoint.json"
		self.cache_dir = ".cache"
		self.__current_temperature = 0
		self.__archive = []
		self.duration = 0
		self.__n_eval = 0
		self.__ideal = None
		self.__nadir = None
		self.__old_norm_objectives = []
		self.__phy = []
		self.__fig = None
		self.__ax = None
		self.__line = None

	def run(self, problem, improve = None, remove_checkpoints = True, plot = False):
		problem.load_cache(self.cache_dir)
		self.__current_temperature = self.__initial_temperature
		self.__archive = []
		self.duration = 0
		self.__n_eval = 0
		self.__ideal = None
		self.__nadir = None
		self.__old_norm_objectives = []
		self.__phy = []
		self.duration = time.time()
		if os.path.exists(self.minimize_checkpoint_file):
			self.__read_checkpoint_minimize(problem)
			problem.archive_to_cache(self.__archive)
		elif os.path.exists(self.hill_climb_checkpoint_file):
			initial_candidate = self.__read_checkpoint_hill_climb(problem)
			problem.archive_to_cache(initial_candidate)
			self.__initial_hill_climbing(problem, initial_candidate)
			if len(self.__archive) > self.__archive_hard_limit:
				self.__archive = AMOSA.clustering(self.__archive, problem, self.__archive_hard_limit, self.__clustering_max_iterations, True)
			self.__save_checkpoint_minimize()
			if remove_checkpoints:
				os.remove(self.hill_climb_checkpoint_file)
		elif improve is not None:
			self.__archive_from_json(problem, improve)
			problem.archive_to_cache(self.__archive)
			if len(self.__archive) > self.__archive_hard_limit:
				self.__archive = AMOSA.clustering(self.__archive, problem, self.__archive_hard_limit, self.__clustering_max_iterations, True)
			self.__save_checkpoint_minimize()
			if remove_checkpoints:
				os.remove(self.hill_climb_checkpoint_file)
		else:
			self.__random_archive(problem)
			self.__save_checkpoint_minimize()
			if remove_checkpoints:
				os.remove(self.hill_climb_checkpoint_file)
		assert len(self.__archive) > 0, "Archive not initialized"
		AMOSA.print_header(problem)
		self.__print_statistics(problem)
		self.__main_loop(problem, plot)
		self.__fig = None
		self.__ax = None
		self.__line = None
		self.__archive = AMOSA.remove_infeasible(problem, self.__archive)
		self.__archive = AMOSA.remove_dominated(self.__archive)
		if len(self.__archive) > self.__archive_hard_limit:
			self.__archive = AMOSA.clustering(self.__archive, problem, self.__archive_hard_limit, self.__clustering_max_iterations, True)
		self.__print_statistics(problem)
		self.duration = time.time() - self.duration
		problem.store_cache(self.cache_dir)
		if remove_checkpoints:
			os.remove(self.minimize_checkpoint_file)

    def pareto_front(self):
        return np.array([s["f"] for s in self.__archive])

    def pareto_set(self):
        return np.array([s["x"] for s in self.__archive])

    def constraint_violation(self):
        return np.array([s["g"] for s in self.__archive])

    def plot_pareto(self, problem, pdf_file, fig_title = "Pareto front", axis_labels = ["f0", "f1", "f2"]):
        F = self.pareto_front()
        if problem.num_of_objectives == 2:
            plt.figure(figsize=(10, 10), dpi=300)
            plt.plot(F[:, 0], F[:, 1], 'k.')
            plt.xlabel(axis_labels[0])
            plt.ylabel(axis_labels[1])
            plt.title(fig_title)
            plt.savefig(pdf_file, bbox_inches='tight', pad_inches=0)
        elif problem.num_of_objectives == 3:
            fig = plt.figure()
            ax = fig.add_subplot(projection='3d')
            ax.set_xlabel(axis_labels[0])
            ax.set_ylabel(axis_labels[1])
            ax.set_zlabel(axis_labels[2])
            plt.title(fig_title)
            ax.scatter(F[:, 0], F[:, 1], F[:, 2], marker='.', color='k')
            plt.tight_layout()
            plt.savefig(pdf_file, bbox_inches='tight', pad_inches=0)

    def save_results(self, problem, csv_file):
        original_stdout = sys.stdout
        row_format = "{:};" * problem.num_of_objectives + "{:};" * problem.num_of_variables
        with open(csv_file, "w") as file:
            sys.stdout = file
            print(row_format.format(*[f"f{i}" for i in range(problem.num_of_objectives)], *[f"x{i}" for i in range(problem.num_of_variables)]))
            for f, x in zip(self.pareto_front(), self.pareto_set()):
                print(row_format.format(*f, *x))
        sys.stdout = original_stdout

    def __parameters_check(self):
        if self.__archive_hard_limit > self.__archive_soft_limit:
            raise RuntimeError("Hard limit must be greater than the soft one")
        if self.__hill_climbing_iterations < 0:
            raise RuntimeError("Initial hill-climbing refinement iterations must be greater or equal than 0")
        if self.__archive_gamma < 1:
            raise RuntimeError("Gamma for initial hill-climbing refinement must be greater than 1")
        if self.__annealing_iterations < 1:
            raise RuntimeError("Refinement iterations must be greater than 1")
        if self.__final_temperature <= 0:
            raise RuntimeError("Final temperature of the matter must be greater or equal to 0")
        if self.__initial_temperature <= self.__final_temperature:
            raise RuntimeError("Initial temperature of the matter must be greater than the final one")
        if self.__cooling_factor <= 0 or self.__cooling_factor >= 1:
            raise RuntimeError("The cooling factor for the temperature of the matter must be in the (0, 1) range")

    def __initialize_archive(self, problem):
        print("Initializing archive...")
        self.__n_eval = self.__archive_gamma * self.__archive_soft_limit * self.__hill_climbing_iterations
        num_of_initial_candidate_solutions = self.__archive_gamma * self.__archive_soft_limit
        initial_candidate_solutions = [lower_point(problem), upper_point(problem)]
        if self.__hill_climbing_iterations > 0:
            for i in range(num_of_initial_candidate_solutions):
                print(f"  {i + 1}/{num_of_initial_candidate_solutions}                                                  ", end = "\r", flush = True)
                initial_candidate_solutions.append(hill_climbing(problem, random_point(problem), self.__hill_climbing_iterations))
        for x in initial_candidate_solutions:
            self.__add_to_archive(x)

    def __add_to_archive(self, x):
        if len(self.__archive) == 0:
            self.__archive.append(x)
        else:
            self.__archive = [y for y in self.__archive if not dominates(x, y)]
            if not any([dominates(y, x) or is_the_same(x, y) for y in self.__archive]):
                self.__archive.append(x)

    def __archive_clustering(self, problem):
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

    def __remove_infeasible(self, problem):
        if problem.num_of_constraints > 0:
            self.__archive = [s for s in self.__archive if all([g <= 0 for g in s["g"]])]

    def __print_header(self, problem):
        if problem.num_of_constraints == 0:
            print("\n  +-{:>12}-+-{:>10}-+-{:>6}-+-{:>10}-+-{:>10}-+-{:>10}-+".format("-" * 12, "-" * 10, "-" * 6, "-" * 10, "-" * 10, "-" * 10))
            print("  | {:>12} | {:>10} | {:>6} | {:>10} | {:>10} | {:>10} |".format("temp.", "# eval", " # nds", "D*", "Dnad", "phi"))
            print("  +-{:>12}-+-{:>10}-+-{:>6}-+-{:>10}-+-{:>10}-+-{:>10}-+".format("-" * 12, "-" * 10, "-" * 6, "-" * 10, "-" * 10, "-" * 10))
        else:
            print("\n  +-{:>12}-+-{:>10}-+-{:>6}-+-{:>6}-+-{:>10}-+-{:>10}-+-{:>10}-+-{:>10}-+-{:>10}-+".format("-" * 12, "-" * 10, "-" * 6, "-" * 6, "-" * 10, "-" * 10, "-" * 10, "-" * 10, "-" * 10))
            print("  | {:>12} | {:>10} | {:>6} | {:>6} | {:>10} | {:>10} | {:>10} | {:>10} | {:>10} |".format("temp.", "# eval", "# nds", "# feas", "cv min", "cv avg", "D*", "Dnad", "phi"))
            print("  +-{:>12}-+-{:>10}-+-{:>6}-+-{:>6}-+-{:>10}-+-{:>10}-+-{:>10}-+-{:>10}-+-{:>10}-+".format("-" * 12, "-" * 10, "-" * 6, "-" * 6, "-" * 10, "-" * 10, "-" * 10, "-" * 10, "-" * 10))

    def __print_statistics(self, problem):
        self.__n_eval += self.__annealing_iterations
        delta_nad, delta_ideal, phy = self.__compute_deltas()
        self.__phy.append(phy)
        if problem.num_of_constraints == 0:
            print("  | {:>12.2e} | {:>10.2e} | {:>6} | {:>10.3e} | {:>10.3e} | {:>10.3e} |".format(self.__current_temperature, self.__n_eval, len(self.__archive), delta_ideal, delta_nad, phy))
        else:
            feasible, cv_min, cv_avg = self.__compute_cv()
            print("  | {:>12.2e} | {:>10.2e} | {:>6} | {:>6} | {:>10.2e} | {:>10.2e} | {:>10.3e} | {:>10.3e} | {:>10.3e} |".format(self.__current_temperature, self.__n_eval, len(self.__archive), feasible, cv_min, cv_avg, delta_ideal, delta_nad, phy))

    def __compute_cv(self):
        g = np.array([s["g"] for s in self.__archive ])
        feasible = np.all(np.less(g, 0), axis=1).sum()
        g = g[np.where(g > 0)]
        return feasible, 0 if len(g) == 0 else np.min(g), 0 if len(g) == 0 else np.average(g)

    def __compute_deltas(self):
        f = np.array([s["f"] for s in self.__archive])
        if self.__nadir is None and self.__ideal is None and self.__old_f is None:
            self.__nadir = np.max(f, axis=0)
            self.__ideal = np.min(f, axis=0)
            self.__old_f = np.array([[(p - i) / (n - i) for p, i, n in zip(x, self.__ideal, self.__nadir) ] for x in f[:] ])
            return np.inf, np.inf, 0
        else:
            nadir = np.max(f, axis=0)
            ideal = np.min(f, axis=0)
            delta_nad = np.max([(nad_t_1 - nad_t) / (nad_t_1 - id_t) for nad_t_1, nad_t, id_t in zip(self.__nadir, nadir, ideal)])
            delta_ideal = np.max([(id_t_1 - id_t) / (nad_t_1 - id_t) for id_t_1, id_t, nad_t_1 in zip(self.__ideal, ideal, self.__nadir)])
            f = np.array([[(p - i) / (n - i) for p, i, n in zip(x, self.__ideal, self.__nadir) ] for x in f[:] ])
            phy = sum([np.min([np.linalg.norm(p - q) for q in f[:]]) for p in self.__old_f[:]]) / len(self.__old_f)
            self.__nadir = nadir
            self.__ideal = ideal
            self.__old_f = f
            return delta_nad, delta_ideal, phy

    def __compute_fitness_range(self, x, y):
        f = [s["f"] for s in self.__archive] + [x["f"], y["f"]]
        return np.max(f, axis = 0) - np.min(f, axis=0)

def hill_climbing(problem, x, max_iterations):
    d, up = hill_climbing_direction(problem)
    for _ in range(max_iterations):
        y = copy.deepcopy(x)
        hill_climbing_adaptive_step(problem, y, d, up)
        if dominates(y, x) and not_the_same(y, x):
            x = y
        else:
            d, up = hill_climbing_direction(problem, d)
    return x

def random_point(problem):
    x = {
        "x": [ l if l == u else random.randrange(l, u) if t == AMOSA.Type.INTEGER else random.uniform(l, u) for l, u, t in zip(problem.lower_bound, problem.upper_bound, problem.types)],
        "f": [0] * problem.num_of_objectives,
        "g": [0] * problem.num_of_constraints if problem.num_of_constraints > 0 else None}
    get_objectives(problem, x)
    return x

def lower_point(problem):
    x = {
        "x": problem.lower_bound,
        "f": [0] * problem.num_of_objectives,
        "g": [0] * problem.num_of_constraints if problem.num_of_constraints > 0 else None}
    get_objectives(problem, x)
    return x

def upper_point(problem):
    x = {
        "x": problem.upper_bound,
        "f": [0] * problem.num_of_objectives,
        "g": [0] * problem.num_of_constraints if problem.num_of_constraints > 0 else None}
    get_objectives(problem, x)
    return x

def random_perturbation(problem, s):
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
            step = random.randrange(lower_bound, 0) if up == -1 else random.randrange(0, upper_bound + 1)
        else:
            step = random.uniform(lower_bound, 0) if up == -1 else random.uniform(0, upper_bound)
    z["x"][d] += step
    get_objectives(problem, z)
    return z

def hill_climbing_direction(problem, c_d = None):
    if c_d is None:
        return random.randrange(0, problem.num_of_variables), 1 if random.random() > 0.5 else -1
    else:
        up = 1 if random.random() > 0.5 else -1
        d = random.randrange(0, problem.num_of_variables)
        while c_d == d:
            d = random.randrange(0, problem.num_of_variables)
        return d, up

def hill_climbing_adaptive_step(problem, s, d, up):
    lower_bound = problem.lower_bound[d] - s["x"][d]
    upper_bound = problem.upper_bound[d] - s["x"][d]
    if (up == -1 and lower_bound == 0) or (up == 1 and upper_bound == 0):
        return 0
    if problem.types[d] == AMOSA.Type.INTEGER:
        step = random.randrange(lower_bound, 0) if up == -1 else random.randrange(0, upper_bound + 1)
        while step == 0:
            step = random.randrange(lower_bound, 0) if up == -1 else random.randrange(0, upper_bound + 1)
    else:
        step = random.uniform(lower_bound, 0) if up == -1 else random.uniform(0, upper_bound)
        while step == 0:
            step = random.uniform(lower_bound, 0) if up == -1 else random.uniform(0, upper_bound)
    s["x"][d] += step
    get_objectives(problem, s)

def do_clustering(archive, hard_limit):
    while len(archive) > hard_limit:
        d = np.array([[np.linalg.norm(np.array(i["f"]) - np.array(j["f"])) if not np.array_equal(np.array(i["x"]), np.array(j["x"])) else np.nan for j in archive] for i in archive])
        try:
            i_min = np.nanargmin(d)
            r = int(i_min / len(archive))
            c = i_min % len(archive)
            del archive[r if np.where(d[r] == np.nanmin(d[r]))[0].size > np.where(d[c] == np.nanmin(d[c]))[0].size else c]
        except:
            # print("Clustering cannot be performed anymore")
            return

def get_objectives(problem, s):
    out = {"f": [0] * problem.num_of_objectives,
           "g": [0] * problem.num_of_constraints if problem.num_of_constraints > 0 else None}
    problem.evaluate(s["x"], out)
    s["f"] = out["f"]
    s["g"] = out["g"]

def is_the_same(x, y):
    return x["x"] == y["x"]

def not_the_same(x, y):
    return x["x"] != y["x"]

def dominates(x, y):
    if x["g"] is None:
        return all( i <= j for i, j in zip(x["f"], y["f"]) ) and any( i < j for i, j in zip(x["f"], y["f"]) )
    else:
        return  ((all(i <= 0 for i in x["f"]) and any(i > 0 for i in y["g"])) or # x is feasible while y is not
                 (any(i > 0 for i in x["g"]) and any(i > 0 for i in y["g"]) and all([ i <= j for i, j in zip(x["g"], y["g"]) ]) and any([ i < j for i, j in zip(x["g"], y["g"]) ])) or #x and y are both infeasible, but x has a lower constraint violation
                 (all(i <= 0 for i in x["g"]) and all(i <= 0 for i in y["g"]) and all([ i <= j for i, j in zip(x["f"], y["f"]) ]) and any([ i < j for i, j in zip(x["f"], y["f"]) ]))) # both are feasible, but x dominates y in the usual sense

def accept(probability):
    return random.random() < probability

def domination_amount(x, y, r):
    return np.prod([ abs(i - j) / k for i, j, k in zip (x["f"], y["f"], r) ])

def sigmoid(x):
    return 1 / (1 + np.exp(np.array(-x, dtype=np.float128)))
