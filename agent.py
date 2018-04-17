""" Agent
Solves the problem presented by the Bandit via reinforcement learning.

TODO: Transition away from Pickle, in favor of JSON Serialization.
"""
import os
import random
from collections import deque
from datetime import datetime

import numpy as np
from keras import backend as K, Sequential
from keras.callbacks import TensorBoard
from keras.layers import Dense
from keras.optimizers import Adam
from tensorflow import Summary
from tensorflow import Tensor, summary

from settings import *

NOW = datetime.utcnow().strftime("%Y%m%d%H%M%S")
LOG_DIR = os.path.abspath(os.path.join("./tf_logs/", f"run-{NOW}"))
TB_CALLBACK = TensorBoard(log_dir=LOG_DIR, histogram_freq=0, write_graph=False, write_images=False)

events = logging.getLogger("events")
metrics = logging.getLogger("metrics")


class Agent:
    """ Deep Reinforcement Agent

    Uses Keras to build a deep neural network capable of solving
    the contextual bandit problem.
    """

    def __init__(self, state_size: int, action_size: int, *, name: str, batch_size: int = 50):
        """ Initialize an Agent.

        :rtype: Agent
        :param state_size: int
        :param action_size: int
        """

        self.state_size = state_size  # The number of attributes the agent will receive.
        self.action_size = action_size  # The number of actions available.
        self.batch_size = batch_size
        self.name = name

        self.save_weights_path = "./save/agents/agent_weights_{}.h5".format(name)
        self.memory = deque(maxlen=2000)
        self.epsilon = 1.0  # Exploration rate
        self.epsilon_min = 0.001
        self.epsilon_decay = 0.15
        self.learning_rate = 0.001
        self.step = 0

        self.model = self._build_model()
        self.writer = summary.FileWriter(LOG_DIR)

    @staticmethod
    def _loss(target: Tensor, prediction: Tensor) -> Tensor:
        """ Calculates loss.

        :param target: The actual result.
        :param prediction: The predicted result.
        :return: The mean squared error of prediction - target.
        """
        error = prediction - target
        return K.mean(K.sqrt(1 + K.square(error)) - 1, axis=-1)

    def _build_model(self) -> Sequential:
        """ Neural net for deep reinforcement learning. """
        # Compute the average between input and output, as a baseline number of neurons.
        hidden_neurons = int((self.state_size + self.action_size) / 2)
        # Build the model.
        model = Sequential()
        model.add(Dense(hidden_neurons, input_dim=self.state_size, activation='relu'))
        model.add(Dense(hidden_neurons, activation='relu'))
        model.add(Dense(self.action_size, activation='linear'))
        model.compile(
            loss=self._loss,
            optimizer=Adam(lr=self.learning_rate),
            metrics=[]
        )
        return model

    def remember(self, state: np.array, action: np.array, runtime: float) -> None:
        """ Stores information about the interaction

        :param state: Context about the application
        :param action: Compiler flag  combination used
        :param runtime: Resulting runtime of benchmark
        """
        self.memory.append((state, action, runtime))
        self.step += 1
        if self.step % 20:
            self.replay()
        return

    def log_stats(self, tag, value):
        """ Logs relevant statistics to TensorBoard. """
        stat = Summary(value=[Summary.Value(tag=f"{self.name}_{tag}", simple_value=value)])
        self.writer.add_summary(stat, self.step)
        self.writer.flush()
        return

    def act(self, state: np.ndarray, num_return: int = 1) -> np.ndarray:
        """ Returns a decision

        The outcome depends on the Agent's epsilon value,
        which decays over time.
        """
        if np.random.rand() <= self.epsilon:
            return np.array([random.randrange(self.action_size)])

        act_values = self.model.predict(state)
        actions = np.argsort(act_values[0])[:num_return]
        return actions

    def replay(self) -> None:
        """ Trains the network

        Via sampled replay of past events.
        """
        batch_size = self.batch_size if self.batch_size < len(self.memory) else len(self.memory)

        mini_batch = random.sample(self.memory, batch_size)

        for state, action, runtime in mini_batch:
            target = self.model.predict(state)
            target[0][action] = runtime
            self.model.fit(state, target, epochs=1, verbose=0, callbacks=[TB_CALLBACK])

        if self.epsilon > self.epsilon_min:
            self.epsilon *= (1 - self.epsilon_decay)
        return

    def __getstate__(self):
        """ Returns values to be pickled. """
        self._save_weights()
        state = self.__dict__.copy()
        del state['model']
        del state['writer']
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.model = self._build_model()
        self._load_weights()
        return

    def _load_weights(self) -> None:
        """ Load model weights """
        try:
            self.model.load_weights(self.save_weights_path)
        except OSError:
            events.info("Model weights not found, training from base-model.")
        return

    def _save_weights(self) -> None:
        """ Save model weights """
        self.model.save_weights(self.save_weights_path)
        return
