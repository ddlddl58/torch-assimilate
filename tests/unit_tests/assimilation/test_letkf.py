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
import numpy as np

# Internal modules
import pytassim.state
import pytassim.observation
from pytassim.assimilation.filter.etkf import ETKFCorr
from pytassim.assimilation.filter.letkf import LETKFCorr, LETKFUncorr
from pytassim.assimilation.filter.etkf_core import ETKFWeightsModule
from pytassim.testing import dummy_obs_operator, DummyLocalization


logging.basicConfig(level=logging.INFO)

BASE_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATA_PATH = os.path.join(os.path.dirname(BASE_PATH), 'data')


class TestLETKFCorr(unittest.TestCase):
    def setUp(self):
        self.algorithm = LETKFCorr()
        state_path = os.path.join(DATA_PATH, 'test_state.nc')
        self.state = xr.open_dataarray(state_path).load()
        obs_path = os.path.join(DATA_PATH, 'test_single_obs.nc')
        self.obs = xr.open_dataset(obs_path).load()
        self.obs.obs.operator = dummy_obs_operator

    def tearDown(self):
        self.state.close()
        self.obs.close()

    def test_gen_weights_return_private(self):
        self.algorithm._gen_weights = 1234
        self.assertEqual(self.algorithm.gen_weights, 1234)

    def test_gen_weights_none_sets_none(self):
        self.algorithm._gen_weights = 1234
        self.algorithm.gen_weights = None
        self.assertIsNone(self.algorithm._gen_weights)

    def test_gen_weights_jit_script(self):
        self.algorithm._gen_weights = None
        module = ETKFWeightsModule(1.2)
        self.algorithm.gen_weights = module
        self.assertIsInstance(self.algorithm._gen_weights,
                              torch.jit.RecursiveScriptModule)

    def test_gen_weights_raises_typeerror(self):
        with self.assertRaises(TypeError):
            self.algorithm.gen_weights = 1234

    def test_wo_localization_letkf_equals_etkf(self):
        etkf = ETKFCorr()
        obs_tuple = (self.obs, self.obs)
        etkf_analysis = etkf.assimilate(self.state, obs_tuple)
        letkf_analysis = self.algorithm.assimilate(self.state, obs_tuple)
        xr.testing.assert_allclose(letkf_analysis, etkf_analysis)

    def test_update_state_returns_valid_state(self):
        obs_tuple = (self.obs, self.obs)
        analysis = self.algorithm.update_state(
            self.state, obs_tuple, self.state, self.state.time[-1].values
        )
        self.assertTrue(analysis.state.valid)

    def test_dummy_localization_returns_equal_grids(self):
        obs_tuple = (self.obs, self.obs)
        prepared_states = self.algorithm._get_states(self.state, obs_tuple)
        obs_weights = (np.abs(prepared_states[-1]-10) < 10).astype(float)[:, 0]
        use_obs = obs_weights > 0

        localization = DummyLocalization()
        ret_use_obs, ret_weights = localization.localize_obs(
            10, prepared_states[-1]
        )

        np.testing.assert_equal(ret_use_obs, use_obs)
        np.testing.assert_equal(ret_weights, obs_weights)

    def test_update_state_uses_localization(self):
        self.algorithm.localization = DummyLocalization()
        ana_time = self.state.time[-1].values
        nr_grid_points = len(self.state.grid)
        obs_tuple = (self.obs, self.obs)
        prepared_states = self.algorithm._get_states(self.state, obs_tuple)
        obs_weights = (np.abs(prepared_states[-1]-10) < 10).astype(float)[:, 0]
        use_obs = obs_weights > 0
        with patch('pytassim.testing.dummy.DummyLocalization.localize_obs',
                  return_value=(use_obs, obs_weights)) as loc_patch:
           _ = self.algorithm.update_state(self.state, obs_tuple,
                                           self.state, ana_time)
        self.assertEqual(loc_patch.call_count, nr_grid_points)

    def test_wo_localization_letkf_equals_etkf_smoothing(self):
        etkf = ETKFCorr(smoother=True)
        self.algorithm.smoother = True
        obs_tuple = (self.obs, self.obs)
        etkf_analysis = etkf.assimilate(self.state, obs_tuple)
        letkf_analysis = self.algorithm.assimilate(self.state, obs_tuple)
        xr.testing.assert_allclose(letkf_analysis, etkf_analysis)

    def test_algorithm_works(self):
        self.algorithm.inf_factor = 1.1
        ana_time = self.state.time[-1].values
        obs_tuple = (self.obs, self.obs.copy())
        assimilated_state = self.algorithm.assimilate(self.state, obs_tuple,
                                                      self.state, ana_time)
        self.assertFalse(np.any(np.isnan(assimilated_state.values)))

    def test_letkfuncorr_sets_correlated_to_false(self):
        self.assertFalse(LETKFUncorr()._correlated)


if __name__ == '__main__':
    unittest.main()
