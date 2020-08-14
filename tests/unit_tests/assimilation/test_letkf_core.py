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
from pytassim.assimilation.utils import evd, rev_evd
from pytassim.assimilation.filter.letkf_core import LETKFAnalyser
from pytassim.assimilation.filter.etkf_core import ETKFWeightsModule, \
    ETKFAnalyser
from pytassim.testing import dummy_obs_operator, DummyLocalization


logging.basicConfig(level=logging.INFO)

BASE_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATA_PATH = os.path.join(os.path.dirname(BASE_PATH), 'data')


class TestLETKFCorr(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        state_path = os.path.join(DATA_PATH, 'test_state.nc')
        state = xr.open_dataarray(state_path).load().isel(time=0)
        obs_path = os.path.join(DATA_PATH, 'test_single_obs.nc')
        obs = xr.open_dataset(obs_path).load().isel(time=0)
        obs.obs.operator = dummy_obs_operator
        pseudo_state = obs.obs.operator(state)
        cls.state_perts = state-state.mean('ensemble')
        cls.normed_perts = torch.from_numpy(
            (pseudo_state - pseudo_state.mean('ensemble')).values
        ).float().view(-1, 40)
        cls.normed_obs = torch.from_numpy(
            (obs['observations'] - pseudo_state.mean('ensemble')).values
        ).float().view(1, 40)
        cls.obs_grid = obs['obs_grid_1'].values.reshape(-1, 1)
        cls.state_grid = state.grid.values.reshape(-1, 1)

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
        self.assertIsInstance(self.analyser._gen_weights, torch.nn.Module)

    def test_dummy_localization_returns_equal_grids(self):
        distance = np.abs(self.obs_grid-10)
        obs_weights = np.clip(1-distance/10, a_min=0, a_max=None)[:, 0]
        use_obs = obs_weights > 0
        ret_use_obs, ret_weights = self.localisation.localize_obs(
            10, self.obs_grid
        )
        np.testing.assert_equal(ret_use_obs, use_obs)
        np.testing.assert_equal(ret_weights, obs_weights)

    def test_localise_states_localises_states(self):
        distance = np.abs(self.obs_grid-10)
        obs_weights = np.sqrt(
            np.clip(1-distance/10, a_min=0, a_max=None)[:, 0]
        )
        use_obs = obs_weights > 0
        obs_weights = obs_weights[use_obs]
        loc_perts = (self.normed_perts[..., use_obs] * obs_weights).float()
        loc_obs = (self.normed_obs[..., use_obs] * obs_weights).float()
        ret_perts, ret_obs = self.analyser._localise_obs(
            10, self.normed_perts, self.normed_obs, self.obs_grid
        )
        torch.testing.assert_allclose(ret_perts, loc_perts)
        torch.testing.assert_allclose(ret_obs, loc_obs)

    def test_localise_states_returns_global_states_if_no_localisation(self):
        self.analyser.localization = None
        ret_perts, ret_obs = self.analyser._localise_obs(
            10, self.normed_perts, self.normed_obs, self.obs_grid
        )
        torch.testing.assert_allclose(ret_perts, self.normed_perts)
        torch.testing.assert_allclose(ret_obs, self.normed_obs)

    def test_get_analysis_perts_returns_loc_analysis_perts(self):
        etkf_analyser = ETKFAnalyser(self.analyser.inf_factor)
        right_perts = []
        for gp in self.state_grid:
            loc_perts, loc_obs = self.analyser._localise_obs(
                gp, self.normed_perts, self.normed_obs, self.obs_grid
            )
            loc_perts = etkf_analyser.get_analysis_perts(
                self.state_perts.sel(grid=gp), loc_perts, loc_obs, None
            )
            right_perts.append(loc_perts)
        right_perts = xr.concat(right_perts, dim='grid')
        right_perts = right_perts.transpose(*self.state_perts.dims)

        ret_perts = self.analyser.get_analysis_perts(
            self.state_perts, self.normed_perts, self.normed_obs, self.obs_grid
        )
        np.testing.assert_almost_equal(ret_perts.values, right_perts.values)

    def test_letkf_analyser_gets_same_solution_as_hunt_07(self):
        use_obs, obs_weights = self.localisation.localize_obs(
            [10, ], self.obs_grid
        )
        use_obs = obs_weights > 0
        obs_weights = torch.from_numpy(obs_weights[use_obs]).float()
        obs_cov = torch.eye(19) * 0.5
        loc_perts = self.normed_perts[..., use_obs]
        loc_obs = self.normed_obs[..., use_obs]

        c_hunt, _ = torch.solve(
            loc_perts.view(1, 10, 19).transpose(-1, -2), obs_cov.view(1, 19, 19)
        )
        c_hunt = c_hunt.squeeze(0).t() * obs_weights
        obs_prec = c_hunt @ loc_perts.t()
        evals, evects, evals_inv, evects_inv = evd(obs_prec, 9)
        cov_analysed = rev_evd(evals_inv, evects, evects_inv)

        evals_perts = (9 * evals_inv).sqrt()
        w_perts = rev_evd(evals_perts, evects, evects_inv)

        w_mean = cov_analysed @ c_hunt @ loc_obs.t()
        weights = w_mean.squeeze() + w_perts
        right_ana_pert = self.state_perts[..., 10].values @ weights.numpy()

        ret_ana_perts = self.analyser.get_analysis_perts(
            self.state_perts[..., [10]], self.normed_perts*np.sqrt(2),
            self.normed_obs*np.sqrt(2),
            self.obs_grid
        ).values.squeeze()
        np.testing.assert_almost_equal(ret_ana_perts, right_ana_pert,
                                       decimal=6)



if __name__ == '__main__':
    unittest.main()
