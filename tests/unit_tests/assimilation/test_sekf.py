#!/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 7/16/19

Created for torch-assimilate

@author: Tobias Sebastian Finn, tobias.sebastian.finn@uni-hamburg.de

    Copyright (C) {2019}  {Tobias Sebastian Finn}

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

# External modules
import xarray as xr
import numpy as np
import pandas as pd

from dask.distributed import LocalCluster, Client

# Internal modules

from pytassim.assimilation.filter.sekf import SEKF
from pytassim.testing import dummy_obs_operator
from pytassim.testing.cases import TestDistributedCase


logging.basicConfig(level=logging.DEBUG)


BASE_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATA_PATH = os.path.join(os.path.dirname(BASE_PATH), 'data')


def dummy_h_jacob():
    pass


class TestSEKF(TestDistributedCase):
    state_path = os.path.join(DATA_PATH, 'test_state.nc')
    obs_path = os.path.join(DATA_PATH, 'test_single_obs.nc')

    def setUp(self) -> None:
        self.b_matrix = np.identity(4) * 0.5
        self.algorithm = SEKF(b_matrix=self.b_matrix, h_jacob=dummy_h_jacob,
                              client=self.client, chunksize=10)
        self.state = self.verticalize_state(self.state, 4)
        self.obs = self.obs.sel(obs_grid_1=(self.obs.obs_grid_1 % 4 == 0),
                                obs_grid_2=(self.obs.obs_grid_2 % 4 == 0))

    @ staticmethod
    def verticalize_state(state, vert_dim=4) -> xr.DataArray:
        state = state.copy()
        vert_grid = state['grid'].values % vert_dim
        hori_grid = state['grid'].values // vert_dim
        zipped_grid = [t for t in zip(hori_grid, vert_grid)]
        multi_grid = pd.MultiIndex.from_tuples(zipped_grid)
        state['grid'] = multi_grid
        return state


if __name__ == '__main__':
    unittest.main()