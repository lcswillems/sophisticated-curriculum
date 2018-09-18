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

    It associates an attention A(i) to each task i:
        A(i) = a_lp(i)
    where a_lp(i) is the absolute learning progress on task i."""

    def __init__(self, return_hists, estimate_lp, convert_into_dist):
        super().__init__(return_hists)

        self.estimate_lp = estimate_lp
        self.convert_into_dist = convert_into_dist

    def __call__(self, returns):
        super().__call__(returns)

        self.lps = self.estimate_lp()
        self.a_lps = numpy.absolute(self.lps)
        self.attentions = self.a_lps

        return self.convert_into_dist(self.attentions)

class MrDistComputer(DistComputer):
    """A distribution computer based on mastering rate.

    It first associates a pre-attention pre_A(i) to each task i:
        pre_A(i) = Mast(Anc_i)^p * ((1-γ) na_lp(i) + γ Pot(i)) * (1 - Mast(Succ_i))
    where:
    - Mast(Anc_i) is the minimum mastering rate over ancestors of task i in graph G;
    - p is the power;
    - na_lp(i) := a_lp(i) / max_i a_lp(i) is the normalized absolute learning progress on i;
    - Pot(i) := 1 - Mast(i) is the potential of learning task i;
    - γ is the potential proportion;
    - Mast(Succ_i) is the mastering rate over successors of task i in graph G.

    Then, it associates an attention A(i) to each task i, that is the attention to
    task i after i has redistributed δ of its pre-attention."""

    def __init__(self, return_hists, init_min_returns, init_max_returns, ret_K, ext_ret_K,
                 estimate_lp, convert_into_dist, G, power, pot_prop, pred_tr):
        super().__init__(return_hists)

        assert ret_K >= ext_ret_K

        self.min_returns = numpy.array(init_min_returns, dtype=numpy.float)
        self.max_returns = numpy.array(init_max_returns, dtype=numpy.float)
        self.ret_K = ret_K
        self.ext_ret_K = ext_ret_K
        self.estimate_lp = estimate_lp
        self.convert_into_dist = convert_into_dist
        self.G = G
        self.power = power
        self.pot_prop = pot_prop
        self.pred_tr = pred_tr

        self.returns = numpy.copy(self.min_returns)

    def update_returns(self):
        for i in range(len(self.returns)):
            _, returns = self.return_hists[i][-max(self.ret_K, self.ext_ret_K):]
            if len(returns) > 0:
                self.returns[i] = numpy.mean(returns[-self.ret_K:])
                if len(returns) >= self.ext_ret_K:
                    mean_return = numpy.mean(returns[-self.ext_ret_K:])
                    self.min_returns[i] = min(self.min_returns[i], mean_return)
                    self.max_returns[i] = max(self.max_returns[i], mean_return)

    def __call__(self, returns):
        super().__call__(returns)

        self.update_returns()

        self.lps = self.estimate_lp()
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
        self.learning_states = (1 - self.pot_prop) * self.na_lps + self.pot_prop * self.pots
        self.pre_attentions = self.anc_mrs**self.power * self.learning_states * (1 - self.succ_mrs)

        self.attentions = numpy.copy(self.pre_attentions)
        for env_id in reversed(list(nx.topological_sort(self.G))):
            predecessors = list(self.G.predecessors(env_id))
            attention_to_predecessors = self.attentions[env_id]*self.pred_tr
            self.attentions[env_id] -= attention_to_predecessors
            if len(predecessors) > 0:
                self.attentions[predecessors] += attention_to_predecessors/len(predecessors)

        return self.convert_into_dist(self.attentions)