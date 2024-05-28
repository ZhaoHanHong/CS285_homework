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

        lens = [len(c) for c in obs]
        max_len = max(lens)
        
        if self.critic is not None:
            values = [self.critic(ob) for ob in obs]
        else:
            values = [torch.zeros([ob.shape[0],1]) for ob in obs]

        values = [np.concatenate((x,np.zeros([max_len-x.shape[0],x.shape[1]])),axis=0) for x in values]
        actions = [np.concatenate((x,np.zeros([max_len-x.shape[0],x.shape[1]])),axis=0) for x in actions]
        rewards = [np.concatenate((x,np.zeros([max_len-x.shape[0],x.shape[1]])),axis=0) for x in rewards ]
        # terminals = [np.concatenate((x,np.zeros([max_len-x.shape[0],x.shape[1]])),axis=0) for x in terminals]
        values = torch.from_numpy(np.stack(values,axis=0)).to(ptu.device)
        actions = torch.from_numpy(np.stack(actions,axis=0)).to(ptu.device)
        rewards = torch.from_numpy(np.stack(rewards,axis=0)).to(ptu.device)
        # terminals = torch.from_numpy(np.stack(terminals,axis=0)).to(ptu.device)

        q_values: Sequence[np.ndarray] = self._calculate_q_vals(rewards)

        advantages: torch.Tensor = self._estimate_advantage(
            rewards, q_values, values
        )

        info: dict = self.actor.update(
            obs=obs,
            actions=actions,
            advantages=advantages,
        )


        if self.critic is not None:
            s=0;n=0
            for _ in range(self.baseline_gradient_steps):
                s+=self.critic.update(obs,q_values)['Baseline Loss'].item()
                n+=1
            critic_info: dict ={'Baseline Loss':s/n}

            info.update(critic_info)

        return info

    def _calculate_q_vals(self, rewards: Sequence[np.ndarray]) -> Sequence[np.ndarray]:
        """Monte Carlo estimation of the Q function."""
        if not self.use_reward_to_go:
            q_values = self._discounted_return(rewards)
        else:
            q_values = self._discounted_reward_to_go(rewards)

        return q_values

    def _estimate_advantage(
        self,
        rewards: torch.Tensor,
        q_values: torch.Tensor,
        values:torch.Tensor
    ) -> torch.Tensor:
        """Computes advantages by (possibly) subtracting a value baseline from the estimated Q-values.

        Operates on flat 1D NumPy arrays.
        """
        if self.critic is None:
            advantages = q_values
        else:
            assert values.shape == q_values.shape

            if self.gae_lambda is None:
                advantages = q_values - values
            else:
                T = rewards.shape[1]-1

                extended_values = torch.cat(values,torch.zeros([values.shape[0],1]),dim=1)
                delta = rewards + self.gamma * extended_values[:,1:] - extended_values[:,:-1]
                if abs(self.gae_lambda)>1e-4:
                    reverse_a = torch.cumsum(((self.gae_lambda*self.gamma)**(-torch.arange(0,T+1)))*delta[::-1])
                    advantages = (reverse_a*((self.gae_lambda*self.gamma)**(torch.arange(0,T+1))))[::-1]
                    
                else:
                    advantages = delta
                
        if self.normalize_advantages:
            advantages = (advantages - advantages.mean(dim=-1,keepdim=True))/advantages.std(dim=-1,keepdim=True)
        return advantages

    def _discounted_return(self, rewards: Sequence[float]) -> Sequence[float]:
        """
        Helper function which takes a list of rewards {r_0, r_1, ..., r_t', ... r_T} and returns
        a list where each index t contains sum_{t'=0}^T gamma^t' r_{t'}

        Note that all entries of the output list should be the exact same because each sum is from 0 to T (and doesn't
        involve t)!
        """
        T = rewards.shape[1]-1
        gam = self.gamma ** np.arange(0,T+1)
        return torch.einsum('t,b->bt',np.ones([T+1]),torch.einsum('t,bt->b',gam,rewards)) # batched


    def _discounted_reward_to_go(self, rewards: Sequence[float]) -> Sequence[float]:
        """
        Helper function which takes a list of rewards {r_0, r_1, ..., r_t', ... r_T} and returns a list where the entry
        in each index t is sum_{t'=t}^T gamma^(t'-t) * r_{t'}.
        """
        T = rewards.shape[1]-1
        reverse_a = torch.cumsum((rewards[:,::-1]*(self.gamma**(-torch.arange(0,T+1)))),dim=-1)
        a = (reverse_a*(self.gamma**(torch.arange(0,T+1))))[:,::-1]
        return a