import itertools
from torch import nn
from torch.nn import functional as F
from torch import optim

import numpy as np
import torch
from torch import distributions

from cs285.infrastructure import pytorch_util as ptu


class MLPPolicy(nn.Module):
    """Base MLP policy, which can take an observation and output a distribution over actions.

    This class should implement the `forward` and `get_action` methods. The `update` method should be written in the
    subclasses, since the policy update rule differs for different algorithms.
    """

    def __init__(
        self,
        ac_dim: int,
        ob_dim: int,
        discrete: bool,
        n_layers: int,
        layer_size: int,
        learning_rate: float,
    ):
        super().__init__()

        if discrete:
            self.logits_net = ptu.build_mlp(
                input_size=ob_dim,
                output_size=ac_dim,
                n_layers=n_layers,
                size=layer_size,
            ).to(ptu.device)
            parameters = self.logits_net.parameters()
        else:
            self.mean_net = ptu.build_mlp(
                input_size=ob_dim,
                output_size=ac_dim,
                n_layers=n_layers,
                size=layer_size,
            ).to(ptu.device)
            self.logstd = nn.Parameter(
                torch.zeros(ac_dim, dtype=torch.float32, device=ptu.device)
            )
            parameters = itertools.chain([self.logstd], self.mean_net.parameters())

        self.optimizer = optim.Adam(
            parameters,
            learning_rate,
        )

        self.discrete = discrete
        print('MLPPolicy.__init__',ob_dim,ac_dim)

    @torch.no_grad()
    def get_action(self, obs: np.ndarray) -> np.ndarray:
        """Takes a single observation (as a numpy array) and returns a single action (as a numpy array)."""
        # TODO: implement get_action
        obs = torch.from_numpy(obs).to(ptu.device).float()
        if self.discrete:
            # print('get_action: disrcete')
            ans = self.logits_net(obs)
            if ans.isnan().any():
                ans=torch.zeros_like(ans)
            ans = torch.distributions.Categorical(torch.softmax(ans,dim=-1)).sample()
        else:
            if len(obs.shape)==1:
                obs = obs.reshape(1,-1)
            ans = torch.distributions.Normal(self.mean_net(obs),torch.exp(self.logstd)).sample()
            if ans.shape[0]==1:
                ans = ans.reshape(-1)

        return ans.detach().cpu().numpy()

    def forward(self, obs: torch.FloatTensor):
        """
        This function defines the forward pass of the network.  You can return anything you want, but you should be
        able to differentiate through it. For example, you can return a torch.FloatTensor. You can also return more
        flexible objects, such as a `torch.distributions.Distribution` object. It's up to you!
        """
        if self.discrete:
            # TODO: define the forward pass for a policy with a discrete action space.
            return self.logits_net(obs)
        else:
            # TODO: define the forward pass for a policy with a continuous action space.
            return torch.distributions.Normal(self.mean_net(obs),torch.exp(self.logstd))
        return None

    def update(self, obs: np.ndarray, actions: np.ndarray, *args, **kwargs) -> dict:
        """Performs one iteration of gradient descent on the provided batch of data."""
        raise NotImplementedError


class MLPPolicyPG(MLPPolicy):
    """Policy subclass for the policy gradient algorithm."""

    def update(
        self,
        obs: torch.Tensor,
        actions: torch.Tensor,
        advantages: torch.Tensor,
    ) -> dict:
        """Implements the policy gradient actor update."""
        # obs = ptu.from_numpy(obs)
        # actions = ptu.from_numpy(actions) 
        # advantages = ptu.from_numpy(advantages) 

        # TODO: implement the policy gradient actor update.
        if self.discrete:
            # print('MLPPolicyPG, update',obs.shape) # [22,4]
            # print('MLPPolicyPG, update',actions.shape)#[22]
            # print('MLPPolicyPG, update',advantages.shape)#[22]
            obs = obs.reshape(-1,obs.shape[-1])
            actions = actions.reshape([-1]).to(torch.long)
            advantages = advantages.reshape([-1])
        
            loss = F.nll_loss(torch.log(F.softmax(self(obs),dim=-1))*advantages.reshape(-1,1),actions)
            if loss.isnan().any():
                print('[INFO]: loss is NAN')
            else:
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
        else:
            # obs = obs.squeeze(0)
            # actions = actions.squeeze(0).to(torch.long)
            # advantages = advantages.squeeze(0).reshape([-1])
            def remove_dim0(t):
                if len(t.shape)==0:
                    return t
                elif len(t.shape)==1:
                    return t.reshape(-1)
                else:
                    return t.reshape([-1]+list(t.shape[2:]))
            obs = remove_dim0(obs)
            actions = remove_dim0(actions)
            advantages = remove_dim0(advantages)
            loss = -self(obs).log_prob(actions)*advantages.reshape(-1,1)
            loss = loss.sum()
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
        return {
            "Actor Loss": ptu.to_numpy(loss),
        }
