from typing import Optional, Sequence
import numpy as np
import torch

from cs285.networks.policies import MLPPolicyPG
from cs285.networks.critics import ValueCritic
from cs285.infrastructure import pytorch_util as ptu
from torch import nn


class PGAgent(nn.Module):
    def __init__(
        self,
        ob_dim: int,
        ac_dim: int,
        discrete: bool,
        n_layers: int,
        layer_size: int,
        gamma: float,
        learning_rate: float,
        use_baseline: bool,
        use_reward_to_go: bool,
        baseline_learning_rate: Optional[float],
        baseline_gradient_steps: Optional[int],
        gae_lambda: Optional[float],
        normalize_advantages: bool,
    ):
        super().__init__()

        # create the actor (policy) network
        self.actor = MLPPolicyPG(
            ac_dim, ob_dim, discrete, n_layers, layer_size, learning_rate
        )

        # create the critic (baseline) network, if needed
        if use_baseline:
            self.critic = ValueCritic(
                ob_dim, n_layers, layer_size, baseline_learning_rate
            )
            self.baseline_gradient_steps = baseline_gradient_steps
        else:
            self.critic = None

        # other agent parameters
        self.gamma = gamma
        self.use_reward_to_go = use_reward_to_go
        self.gae_lambda = gae_lambda
        self.normalize_advantages = normalize_advantages

    def update(
        self,
        obs: Sequence[np.ndarray],
        actions: Sequence[np.ndarray],
        rewards: Sequence[np.ndarray],
        terminals: Sequence[np.ndarray],
    ) -> dict:
        """The train step for PG involves updating its actor using the given observations/actions and the calculated
        qvals/advantages that come from the seen rewards.

        Each input is a list of NumPy arrays, where each array corresponds to a single trajectory. The batch size is the
        total number of samples across all trajectories (i.e. the sum of the lengths of all the arrays).
        """

        # step 1: calculate Q values of each (s_t, a_t) point, using rewards (r_0, ..., r_t, ..., r_T)
        # rewards = np.concatenate(tuple(rewards),axis=0)
        # print(rewards.shape) # [batch,]
        q_values: Sequence[np.ndarray] = self._calculate_q_vals(rewards)

        # TODO: flatten the lists of arrays into single arrays, so that the rest of the code can be written in a vectorized
        # way. obs, actions, rewards, terminals, and q_values should all be arrays with a leading dimension of `batch_size`
        # beyond this point.
        obs = np.concatenate(obs,axis=0) # [batch,4]
        actions = np.concatenate(actions,axis=0) # [batch,]
        terminals = np.concatenate(terminals,axis=0) # [batch,]
        rewards = np.concatenate(rewards,axis=0) # [batch,]

        # step 2: calculate advantages from Q values
        advantages: np.ndarray = self._estimate_advantage(
            obs, rewards, q_values, terminals
        )

        # step 3: use all datapoints (s_t, a_t, adv_t) to update the PG actor/policy
        # TODO: update the PG actor/policy network once using the advantages
        info: dict = self.actor.update(
            obs=obs,
            actions=actions,
            advantages=advantages,
        )


        # step 4: if needed, use all datapoints (s_t, a_t, q_t) to update the PG critic/baseline
        if self.critic is not None:
            # TODO: perform `self.baseline_gradient_steps` updates to the critic/baseline network
            critic_info: dict ={'Baseline Loss':[]}
            for _ in self.baseline_gradient_steps:
                critic_info['Baseline Loss'].append(self.critic.update(obs,q_values))

            info.update(critic_info)

        return info

    def _calculate_q_vals(self, rewards: Sequence[np.ndarray]) -> Sequence[np.ndarray]:
        """Monte Carlo estimation of the Q function."""
        print('rewards',rewards)
        print('len(rewards)',len(rewards))
        print('rewards[0].shape',rewards[0].shape)
        if not self.use_reward_to_go:
            # Case 1: in trajectory-based PG, we ignore the timestep and instead use the discounted return for the entire
            # trajectory at each point.
            # In other words: Q(s_t, a_t) = sum_{t'=0}^T gamma^t' r_{t'}
            # TODO: use the helper function self._discounted_return to calculate the Q-values
            q_values = self._discounted_return(rewards)
        else:
            # Case 2: in reward-to-go PG, we only use the rewards after timestep t to estimate the Q-value for (s_t, a_t).
            # In other words: Q(s_t, a_t) = sum_{t'=t}^T gamma^(t'-t) * r_{t'}
            # TODO: use the helper function self._discounted_reward_to_go to calculate the Q-values
            q_values = self._discounted_reward_to_go(rewards)

        return q_values

    def _estimate_advantage(
        self,
        obs: np.ndarray,
        rewards: np.ndarray,
        q_values: np.ndarray,
        terminals: np.ndarray,
    ) -> np.ndarray:
        """Computes advantages by (possibly) subtracting a value baseline from the estimated Q-values.

        Operates on flat 1D NumPy arrays.
        """
        if self.critic is None:
            # TODO: if no baseline, then what are the advantages?
            # print('TODO: if no baseline, then what are the advantages?')
            advantages = q_values
        else:
            # TODO: run the critic and use it as a baseline
            # print('TODO: if no baseline, then what are the advantages?')
            values = self.critic(obs)
            assert values.shape == q_values.shape

            if self.gae_lambda is None:
                # print('if using a baseline, but not GAE, what are the advantages?')
                # TODO: if using a baseline, but not GAE, what are the advantages?
                advantages = q_values - values
            else:
                # TODO: implement GAE
                batch_size = obs.shape[0]

                # HINT: append a dummy T+1 value for simpler recursive calculation
                values = np.append(values, [0])
                advantages = np.zeros(batch_size + 1)

                for i in reversed(range(batch_size)):
                    # TODO: recursively compute advantage estimates starting from timestep T.
                    # HINT: use terminals to handle edge cases. terminals[i] is 1 if the state is the last in its
                    # trajectory, and 0 otherwise.
                    
                    # batch size = T+1
                    # i starts from T, ends to 0
                    raise NotImplementedError()
                    T = batch_size-1
                    if terminals[i]:
                        advantages[i]=advantages[i+1]+rewards[T]-values[T]
                    else:
                        advantages[i]=advantages[i+1]+(rewards[T]-values[T]+self.gamma*values[T+1])*((self.gamma*self.gae_lambda)**(T-i))

                # remove dummy advantage
                advantages = advantages[:-1]

        # TODO: normalize the advantages to have a mean of zero and a standard deviation of one within the batch
        if self.normalize_advantages:
            advantages = (advantages - advantages.mean())/advantages.std()
        return advantages

    def _discounted_return(self, rewards: Sequence[float]) -> Sequence[float]:
        """
        Helper function which takes a list of rewards {r_0, r_1, ..., r_t', ... r_T} and returns
        a list where each index t contains sum_{t'=0}^T gamma^t' r_{t'}

        Note that all entries of the output list should be the exact same because each sum is from 0 to T (and doesn't
        involve t)!
        """
        l = []
        for reward in rewards:
            T = len(reward)-1
            gam = self.gamma ** np.arange(0,T+1)
            l.append(np.ones_like(reward)*np.sum(gam*reward))
        return np.concatenate(l,axis=0)
        # return torch.einsum('t,b->bt',np.ones([T+1]),torch.einsum('t,bt->b',gam,rewards)) # batched


    def _discounted_reward_to_go(self, rewards: Sequence[float]) -> Sequence[float]:
        """
        Helper function which takes a list of rewards {r_0, r_1, ..., r_t', ... r_T} and returns a list where the entry
        in each index t is sum_{t'=t}^T gamma^(t'-t) * r_{t'}.
        """
        l = []
        for reward in rewards:
            T = len(reward)-1
            gam = self.gamma ** np.arange(0,T+1)
            mask = (np.arange(0,T+1).reshape(-1,1)>=np.arange(0,T+1).reshape(1,-1)).astype(np.float32) # mask[i,j]=1 iff i>=j
            ans = np.einsum('pt,t,p->t',mask,gam**-1,gam*reward)
            l.append(ans)
        # ans = np.einsum('pt,t,p,bp->bt',mask,gam**-1,gam,rewards) # batched
        return np.concatenate(l,axis=0)
