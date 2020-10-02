import os
import signal
import time
import datetime
import yaml
try:
    from tqdm import trange
except ModuleNotFoundError:
    trange = range

import torch
import gym
#import gym_hypercube
import matplotlib.pyplot as plt

from commons.utils import NormalizedActions, get_latest_dir

from cfd.flatplate.flatplate import FlatPlate
from cfd.starccm.CFDcommunication import CFDcommunication

def load_config(path):
    with open(path, 'r') as file:
        config = yaml.safe_load(file)
    if type(config['GAME']) == str:
        config['GAME'] = {'id': config['GAME']}
    return config


def create_folder(algo_name, game, config):

    current_time = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    folder = f'results/{algo_name}/{game}_{current_time}'

    # Create folder
    if not os.path.exists(f'{folder}/models/'):
        os.makedirs(f'{folder}/models/')

    # Save config
    with open(f'{folder}/config.yaml', 'w') as file:
        yaml.dump(config, file)

    return folder


def train(Agent, args):
    #config = load_config(f'agents/{args.agent}/config.yaml')
    # TO DO update path for generic name
    #config = load_config(f'cfd/flatplate/config.yaml')
    config = load_config(f'cfd/starccm/config.yaml')
    
    game = config['GAME']['id'].split('-')[0]
    folder = create_folder(args.agent, game, config)

    if args.load:
        config = load_config(f'{folder}/config.yaml')

    if args.gpu and torch.cuda.is_available():
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')
    print(f"\033[91m\033[1mDevice : {device}\nFolder : {folder}\033[0m")

    # Create gym environment and agent
    if config["GAME"]["id"] == "STARCCMexternalfiles":
        env = NormalizedActions(CFDcommunication(config))
    elif config["GAME"]["id"] == "flatplate":
        env = NormalizedActions(FlatPlate(config))
    else:
        env = NormalizedActions(gym.make(**config['GAME']))
    model = Agent(device, folder, config)

    # Load model from a previous run
    if args.load:
        model.load(args.load)

    # Signal to render evaluation during training by pressing CTRL+Z
    def handler(sig, frame):
        model.evaluate(n_ep=1, render=True)
        # model.plot_Q(pause=True)
    signal.signal(signal.SIGTSTP, handler)

    nb_total_steps = 0
    nb_episodes = 0

    print("Starting training...")
    rewards = []
    eval_rewards = []
    lenghts = []
    time_beginning = time.time()

    try:
        for episode in trange(config["MAX_EPISODES"]):

            done = False
            step = 0
            episode_reward = 0

            state = env.reset()

            while not done and step < config["MAX_STEPS"]:

                action = model.select_action(state, episode=episode)
                
                if config["GAME"]["id"] == "STARCCMexternalfiles":
                    env.finishCFD()
                
                next_state, reward, done, _ = env.step(action)
                episode_reward += reward

                if config["GAME"]["id"] == "STARCCMexternalfiles":
                    #set as done if the number of maximum steps is reached even if not
                    #reached the final position to avoid the simulation to continue
                    if not done and step == config["MAX_STEPS"] - 1:
                        done = True
                

                # Save transition into memory
                model.memory.push(state, action, reward, next_state, done)
                state = next_state

                losses = model.optimize()

                step += 1
                nb_total_steps += 1

            rewards.append(episode_reward)
            lenghts.append(step)

            # Sand SAVE variables at the end of episode
            env.fill_array_tobesaved()

            if episode % config["FREQ_SAVE"] == 0:
                model.save()

            if episode % config["FREQ_EVAL"] == 0:
                eval_rewards.append(model.evaluate())

                plt.cla()
                plt.title(folder.rsplit('/', 1)[1])
                absc = range(0, len(eval_rewards*config["FREQ_EVAL"]), config["FREQ_EVAL"])
                plt.plot(absc, eval_rewards)
                plt.savefig(f'{folder}/eval_rewards.png')

            if episode % config["FREQ_PLOT"] == 0:

                plt.cla()
                plt.title(folder.rsplit('/', 1)[1])
                plt.plot(rewards)
                plt.savefig(f'{folder}/rewards.png')

                plt.cla()
                plt.title(folder.rsplit('/', 1)[1])
                plt.plot(lenghts)
                plt.savefig(f'{folder}/lenghts.png')

                plt.close()

            nb_episodes += 1

    except KeyboardInterrupt:
        pass

    finally:
        # DUMP variables at the end of training
        env.print_array_in_files(folder)
        env.plot_training_output(rewards, folder)
        env.close()
        model.save()
        if config["GAME"]["id"] == "STARCCMexternalfiles":
            #end simulation of STARCCM+
            env.finishCFD(True)

    time_execution = time.time() - time_beginning

    print('---------------------------------------------------\n'
          '---------------------STATS-------------------------\n'
          '---------------------------------------------------\n',
          nb_total_steps, ' steps and updates of the network done\n',
          nb_episodes, ' episodes done\n'
          'Execution time : ', round(time_execution, 2), ' seconds\n'
          '---------------------------------------------------\n'
          'Average nb of steps per second : ', round(nb_total_steps/time_execution, 3), 'steps/s\n'
          'Average duration of one episode : ', round(time_execution/max(1, nb_episodes), 3), 's\n'
          '---------------------------------------------------')


def test(Agent, args):

    if args.folder is None:
        agent_folder = f'results/{args.agent}'
        args.folder = os.path.join(get_latest_dir(agent_folder))

    with open(os.path.join(args.folder, 'config.yaml'), 'r') as file:
        config = yaml.safe_load(file)

    device = torch.device('cpu')

    # Creating neural networks and loading models
    print(f"Testing \033[91m\033[1m{args.agent}\033[0m saved in the folder {args.folder}")
    model = Agent(device, args.folder, config)
    model.load()

    score = model.evaluate(n_ep=args.nb_tests, render=args.render, gif=args.gif, test=True)
    print(f"Average score : {score}")
