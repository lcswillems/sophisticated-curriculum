from abc import ABC, abstractmethod
import numpy
import networkx as nx

class DistComputer(ABC):
    """A distribution computer.

    It receives returns for some environments, updates the return history
    given by each environment and computes a distribution over
    environments given these histories of return."""

    def __init__(self, return_hists):
        self.return_hists = return_hists

        self.step = 0

    @abstractmethod
    def __call__(self, returns):
        self.step += 1
        for env_id, returnn in returns.items():
            self.return_hists[env_id].append(self.step, returnn)

class LpDistComputer(DistComputer):
    """A distribution computer based on learning progress.

    It associates an attention a_i to each environment i that is equal
    to the learning progress of this environment, i.e. a_i = lp_i."""

    def __init__(self, return_hists, compute_lp, create_dist):
        super().__init__(return_hists)

        self.compute_lp = compute_lp
        self.create_dist = create_dist

    def __call__(self, returns):
        super().__call__(returns)

        self.lps = self.compute_lp()
        self.a_lps = numpy.absolute(self.lps)
        self.attentions = self.a_lps

        return self.create_dist(self.attentions)

class LpPotDistComputer(DistComputer):
    def __init__(self, return_hists, init_returns, init_max_returns, K,
                 compute_lp, create_dist, pot_coef):
        super().__init__(return_hists)

        self.returns = numpy.array(init_returns, dtype=numpy.float)
        self.max_returns = numpy.array(init_max_returns, dtype=numpy.float)
        self.K = K
        self.compute_lp = compute_lp
        self.create_dist = create_dist
        self.pot_coef = pot_coef

        self.saved_max_returns = self.max_returns[:]

    def update_returns(self):
        for i in range(len(self.returns)):
            _, returns = self.return_hists[i][-self.K:]
            if len(returns) > 0:
                self.returns[i] = returns[-1]
                mean_return = numpy.mean(returns)
                self.max_returns[i] = max(self.saved_max_returns[i], mean_return)
                if len(returns) >= self.K:
                    self.saved_max_returns[i] = self.max_returns[i]

    def __call__(self, returns):
        super().__call__(returns)

        self.update_returns()

        self.returns = numpy.clip(self.returns, None, self.max_returns)
        self.lps = self.compute_lp()
        self.a_lps = numpy.absolute(self.lps)
        self.pots = self.max_returns - self.returns
        self.attentions = self.a_lps + self.pot_coef * self.pots

        return self.create_dist(self.attentions)

class LpPotRrDistComputer(DistComputer):
    def __init__(self, return_hists, init_returns, init_max_returns, K,
                 compute_lp, create_dist, pot_coef, G):
        super().__init__(return_hists)

        self.returns = numpy.array(init_returns, dtype=numpy.float)
        self.max_returns = numpy.array(init_max_returns, dtype=numpy.float)
        self.K = K
        self.compute_lp = compute_lp
        self.create_dist = create_dist
        self.pot_coef = pot_coef
        self.G = G

        self.min_returns = self.returns[:]
        self.saved_min_returns = self.min_returns[:]
        self.saved_max_returns = self.max_returns[:]

    def update_returns(self):
        for i in range(len(self.returns)):
            _, returns = self.return_hists[i][-self.K:]
            if len(returns) > 0:
                self.returns[i] = returns[-1]
                mean_return = numpy.mean(returns)
                self.min_returns[i] = min(self.saved_min_returns[i], mean_return)
                self.max_returns[i] = max(self.saved_max_returns[i], mean_return)
                if len(returns) >= self.K:
                    self.saved_min_returns[i] = self.min_returns[i]
                    self.saved_max_returns[i] = self.max_returns[i]

    def __call__(self, returns):
        super().__call__(returns)

        self.update_returns()

        self.returns = numpy.clip(self.returns, self.min_returns, self.max_returns)
        self.lps = self.compute_lp()
        self.a_lps = numpy.absolute(self.lps)
        self.pots = self.max_returns - self.returns
        self.rrs = (self.returns - self.min_returns) / (self.max_returns - self.min_returns)
        self.filters = numpy.ones(len(self.return_hists))
        for env_id in self.G.nodes:
            ancestors = list(nx.ancestors(self.G, env_id))
            if len(ancestors) > 0:
                self.filters[env_id] = numpy.amin(self.rrs[ancestors])
        self.attentions = self.a_lps + self.pot_coef * self.pots
        self.filtered_attentions = self.attentions * self.filters

        return self.create_dist(self.filtered_attentions)

class NlpPotMancRdDistComputer(DistComputer):
    def __init__(self, return_hists, init_returns, init_max_returns, K,
                 compute_lp, create_dist, pot_coef, G, power, tr):
        super().__init__(return_hists)

        self.returns = numpy.array(init_returns, dtype=numpy.float)
        self.max_returns = numpy.array(init_max_returns, dtype=numpy.float)
        self.K = K
        self.compute_lp = compute_lp
        self.create_dist = create_dist
        self.pot_coef = pot_coef
        self.G = G
        self.power = power
        self.tr = tr

        self.min_returns = self.returns[:]
        self.saved_min_returns = self.min_returns[:]
        self.saved_max_returns = self.max_returns[:]

    def update_returns(self):
        for i in range(len(self.returns)):
            _, returns = self.return_hists[i][-self.K:]
            if len(returns) > 0:
                self.returns[i] = returns[-1]
                mean_return = numpy.mean(returns)
                self.min_returns[i] = min(self.saved_min_returns[i], mean_return)
                self.max_returns[i] = max(self.saved_max_returns[i], mean_return)
                if len(returns) >= self.K:
                    self.saved_min_returns[i] = self.min_returns[i]
                    self.saved_max_returns[i] = self.max_returns[i]

    def __call__(self, returns):
        super().__call__(returns)

        self.update_returns()

        self.returns = numpy.clip(self.returns, self.min_returns, self.max_returns)
        self.lps = self.compute_lp()
        self.a_lps = numpy.absolute(self.lps)
        self.na_lps = self.a_lps / numpy.amax(self.a_lps) if numpy.amax(self.a_lps) != 0 else self.a_lps
        self.mrs = (self.returns - self.min_returns) / (self.max_returns - self.min_returns)
        self.pots = 1 - self.mrs
        self.anc_mrs = numpy.ones(len(self.return_hists))
        for env_id in self.G.nodes:
            ancestors = list(nx.ancestors(self.G, env_id))
            if len(ancestors) > 0:
                self.anc_mrs[env_id] = numpy.amin(self.mrs[ancestors])
        self.succ_mrs = numpy.zeros(len(self.return_hists))
        for env_id in self.G.nodes:
            successors = list(self.G.successors(env_id))
            if len(successors) > 0:
                self.succ_mrs[env_id] = numpy.amin(self.mrs[successors])
        self.learning_states = self.na_lps + self.pot_coef * self.pots
        self.attentions = self.anc_mrs**self.power * self.learning_states * (1-self.succ_mrs)

        self.rd_attentions = self.attentions[:]
        for env_id in reversed(list(nx.topological_sort(self.G))):
            predecessors = list(self.G.predecessors(env_id))
            attention_to_transfer = self.rd_attentions[env_id]*self.tr
            self.rd_attentions[env_id] -= attention_to_transfer
            if len(predecessors) > 0:
                self.rd_attentions[predecessors] += attention_to_transfer/len(predecessors)

        return self.create_dist(self.rd_attentions)