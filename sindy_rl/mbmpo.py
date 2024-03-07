import os
import numpy as np
import gymnasium as gym
from gymnasium.envs.classic_control import PendulumEnv

from ray.rllib.algorithms.mbmpo import MBMPOConfig, MBMPO
from ray.rllib.algorithms.mbmpo.model_ensemble import DynamicsEnsembleCustomModel
from ray.tune.registry import register_env
from ray import tune, air

from sindy_rl import _parent_dir
from sindy_rl.registry import  DMCEnvWrapper
from sindy_rl.reward_fns import cart_reward

_MAX_EP_STEPS = 300

class MBMPOCart(DMCEnvWrapper):
    '''A wrapper to make this compatibile with RLlib's
    MBMPO compatability.
    '''
    
    # need this to tell MBMPO how many steps to run before reset
    # https://github.com/ray-project/ray/issues/39660
    # https://github.com/ray-project/ray/pull/39654
    
    _max_episode_steps = _MAX_EP_STEPS
    
    def __init__(self, config=None):
        if config is None:
            config = {}

        default_cart_config = {      
            'domain_name': "cartpole",
            'task_name': "swingup",
            'frame_skip': 1,
            'from_pixels': False,
            'task_kwargs':{
                'time_limit': 3 # DEFAULT IS 10!
            }
        }
        
        default_cart_config.update(config)
        env_config = default_cart_config
        
        # if env_config.get('use_bounds', None):
        #     self.use_bounds = env_config.pop('use_bounds')
        # else:
        #     self.use_bounds = False

        super().__init__(env_config)

    def reward(self, obs, action, obs_next):
        costs = np.array([cart_reward(x, u) for x, u in zip(obs_next, action)])
        return costs
    
    # Can't actually provide callbacks or boundaries
    # inside the dynamics updates!
    # def step(self, action):
    #     '''Incorporating extra callbacks and reset conditions'''
    #     obs, rew, term, trun, info = super().step(action)
        
    #     obs = project_cartpole(obs)
    #     term = term or self.is_term(obs)
        
    #     return obs, rew, term, trun, info 

    # def is_term(self, obs):
    #     term = False
    #     if self.use_bounds:
    #         lower_bounds_done = np.any(obs <= self.obs_bounds[0])
    #         upper_bounds_done = np.any(obs >= self.obs_bounds[1])
    #         term = lower_bounds_done or upper_bounds_done
    #     return term
    


dynamics_model = {
            "custom_model": DynamicsEnsembleCustomModel,
            # Number of Transition-Dynamics (TD) models in the ensemble.
            "ensemble_size": 5,
            # Hidden layers for each model in the TD-model ensemble.
            "fcnet_hiddens": [512, 512],
            # Model learning rate.
            "lr": 1e-3,
            # Max number of training epochs per MBMPO iter.
            "train_epochs": 500, #500
            # Model batch size.
            "batch_size": 500,
            # Training/validation split.
            "valid_split_ratio": 0.2,
            # Normalize data (obs, action, and deltas).
            "normalize_data": True,
        }

config = MBMPOConfig()
config = (config.training(lr=0.0003, dynamics_model=dynamics_model)
                .environment(env=MBMPOCart)
                # .environment(env_config=env_config)
                .rollouts(num_rollout_workers=1)
                .resources(num_cpus_per_worker=3)
                # .evaluation(
                #             # evaluation_config={'explore': False}, 
                #             evaluation_duration=5, 
                #             evaluation_interval=1, 
                #             evaluation_duration_unit='episodes', 
                #             always_attach_evaluation_results=True)
                .rl_module(_enable_rl_module_api=False)
            )

# update model size
model_config = config.model
fcnet_hiddens = [32, 32]

model_config.update({'fcnet_hiddens': fcnet_hiddens})
config.training(model=model_config)

# algo = config.build(env=MBMPOCart)
# res = algo.train()

LOCAL_DIR =  os.path.join(_parent_dir, 'ray_results', 'mbmpo')

run_config=air.RunConfig(
    local_dir=LOCAL_DIR,
    name='dmc-cart-test_dyn-nn=512_policy-nn=32_steps=300',
    stop={'training_iteration': 5000},
    log_to_file=True,
    checkpoint_config=air.CheckpointConfig(
        checkpoint_frequency=10),
)

tune_config=tune.TuneConfig(num_samples=20,
                            # scheduler=pbt_sched,
                            )

tuner = tune.Tuner(
    MBMPO,
    param_space=config, # this is what is passed to the experiment
    run_config=run_config,
    tune_config=tune_config,
)
results = tuner.fit()