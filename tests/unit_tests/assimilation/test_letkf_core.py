#!/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 12/7/18

Created for torch-assimilate

@author: Tobias Sebastian Finn, tobias.sebastian.finn@uni-hamburg.de

    Copyright (C) {2018}  {Tobias Sebastian Finn}

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
# System modules
import unittest
import logging
import os
from unittest.mock import patch

# External modules
import xarray as xr
import torch
import torch.jit
import numpy as np

# Internal modules
import pytassim.state
import pytassim.observation
from pytassim.assimilation.filter.letkf_core import LETKFAnalyser
from pytassim.assimilation.filter.etkf_core import ETKFWeightsModule
from pytassim.testing import dummy_obs_operator, DummyLocalization


logging.basicConfig(level=logging.INFO)

BASE_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATA_PATH = os.path.join(os.path.dirname(BASE_PATH), 'data')


class TestLETKFCorr(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        state_path = os.path.join(DATA_PATH, 'test_state.nc')
        state = xr.open_dataarray(state_path).load()
        obs_path = os.path.join(DATA_PATH, 'test_single_obs.nc')
        obs = xr.open_dataset(obs_path).load()
        obs.obs.operator = dummy_obs_operator
        pseudo_state = obs.obs.operator(state)
        cls.normed_perts = torch.from_numpy(
            (pseudo_state - pseudo_state.mean('ensemble')).values
        ).float()
        cls.normed_obs = torch.from_numpy(
            (obs['observations'] - pseudo_state.mean('ensemble')).values
        ).float()
        cls.obs_grid = obs['obs_grid_1'].values
        cls.state_grid = state.grid.values

    def setUp(self):
        self.localisation = DummyLocalization()
        self.analyser = LETKFAnalyser(localization=self.localisation)

    def test_gen_weights_returns_private(self):
        self.assertNotEqual(self.analyser.gen_weights, 12345)
        self.analyser._gen_weights = 12345
        self.assertEqual(self.analyser.gen_weights, 12345)

    def test_gen_weights_sets_gen_weights_to_none(self):
        self.assertIsNotNone(self.analyser._gen_weights)
        self.analyser.gen_weights = None
        self.assertIsNone(self.analyser._gen_weights)

    def test_gen_weights_raises_type_error_if_wrong(self):
        with self.assertRaises(TypeError):
            self.analyser.gen_weights = 12345

    def test_gen_weights_sets_new_module_to_jit(self):
        self.analyser._gen_weights = None
        new_module = ETKFWeightsModule(1.0)
        self.analyser.gen_weights = new_module
        self.assertIsNotNone(self.analyser._gen_weights)
        self.assertIsInstance(self.analyser._gen_weights,
                              torch.jit.RecursiveScriptModule)


if __name__ == '__main__':
    unittest.main()
