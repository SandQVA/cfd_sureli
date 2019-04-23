import os
import time
from datetime import datetime
import argparse
try:
    from tqdm import trange
except ModuleNotFoundError:
    trange = range

import numpy as np
import gym
import yaml

import torch
from tensorboardX import SummaryWriter

from model import Model
from Agent import Agent


print("DQN starting...")

with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)

parser = argparse.ArgumentParser(description='Run DQN on ' + config["GAME"])
parser.add_argument('--gpu', action='store_true', help='Use GPU')
args = parser.parse_args()

# Create folder and writer to write tensorboard values
current_time = datetime.now().strftime('%b%d_%H-%M-%S')
expe_name = f'runs/{current_time}_{config["GAME"][:4]}'
writer = SummaryWriter(expe_name)
if not os.path.exists(expe_name+'/models/'):
    os.mkdir(expe_name+'/models/')

# Write optional info about the experiment to tensorboard
for k, v in config.items():
    writer.add_text('Config', str(k) + ' : ' + str(v), 0)

with open(expe_name+'/config.yaml', 'w') as file:
    yaml.dump(config, file)

# Choose device cpu or cuda if a gpu is available
if args.gpu and torch.cuda.is_available():
    device = 'cuda'
else:
    device = 'cpu'
print("\033[91m\033[1mDevice : ", device.upper(), "\033[0m")
writer.add_text('Device', device, 0)
device = torch.device(device)


# Create gym environment
print("Creating environment...")
env = gym.make(config["GAME"])

STATE_SIZE = env.observation_space.shape[0]
ACTION_SIZE = env.action_space.n

def train():

    print("Creating neural networks and optimizers...")
    model = Model(device, STATE_SIZE, ACTION_SIZE, expe_name, config)

    nb_total_steps = 0
    time_beginning = time.time()

    try:
        print("Starting training...")
        nb_episodes_done = 0
        for episode in trange(config["MAX_EPISODES"]):

            state = env.reset()
            state = torch.tensor([state], dtype=torch.float, device=device)
            done = False
            step = 0
            current_reward = 0

            while not done and step < config["MAX_STEPS"]:

                action = model.select_action(state, episode)

                # Perform an action
                next_state, reward, done, _ = env.step(action.item())
                next_state = torch.tensor([next_state], dtype=torch.float, device=device)
                reward = torch.tensor([reward], device=device)
                current_reward += reward.item()

                if not done and step == config["MAX_STEPS"]:
                    done = True

                # Save transition into memory
                model.memory.push(state, action, reward, next_state)#, 1-int(done))
                state = next_state

                loss = model.optimize(nb_episodes_done, step)

                step += 1
                nb_total_steps += 1

            print('episode : ', episode, ', current_reward : ', current_reward, ', loss : ', loss)
            writer.add_scalar('stats/reward_per_episode', current_reward, episode)
            if loss is not None:
                writer.add_scalar('stats/loss', loss, episode)

            nb_episodes_done += 1

    except KeyboardInterrupt:
        pass

    finally:
        model.save()
        print("\033[91m\033[1mModel saved in", expe_name, "\033[0m")

    time_execution = time.time() - time_beginning

    print('---------------------------------------------------\n'
          '---------------------STATS-------------------------\n'
          '---------------------------------------------------\n',
          nb_total_steps, ' steps and updates of the network done\n',
          nb_episodes_done, ' episodes done\n'
          'Execution time ', round(time_execution, 2), ' seconds\n'
          '---------------------------------------------------\n'
          'Average nb of steps per second : ', round(nb_total_steps/time_execution, 3), 'steps/s\n'
          'Average duration of one episode : ', round(time_execution/nb_episodes_done, 3), 's\n'
          '---------------------------------------------------')

    writer.close()


if __name__ == '__main__':
    train()