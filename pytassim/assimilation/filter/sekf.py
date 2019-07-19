#!/bin/env python
# -*- coding: utf-8 -*-
#
# Created on 7/17/19
#
# Created for torch-assimilate
#
# @author: Tobias Sebastian Finn, tobias.sebastian.finn@uni-hamburg.de
#
#    Copyright (C) {2019}  {Tobias Sebastian Finn}
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

# System modules
import logging

# External modules
import torch
import numpy as np

# Internal modules
from .filter import FilterAssimilation
from pytassim.utilities import chol_solve


logger = logging.getLogger(__name__)


def estimate_inc_uncorr(innov, h_jacob, cov_back, obs_err):
    ht = h_jacob.transpose(-1, -2)
    hb = torch.mm(h_jacob, cov_back)
    innov_prec = torch.mm(hb, ht)
    mat_size = innov_prec.size()[1]
    step = mat_size + 1
    end = mat_size * mat_size
    innov_prec.view(-1)[:end:step] += torch.pow(obs_err, 2)
    norm_innov = chol_solve(innov_prec, innov).t()
    k_dist = torch.mm(cov_back, ht)
    inc_ana = torch.mm(k_dist, norm_innov).squeeze(-1)
    return inc_ana


def estimate_inc_corr(innov, h_jacob, cov_back, cov_obs):
    ht = h_jacob.transpose(-1, -2)
    hb = torch.mm(h_jacob, cov_back)
    innov_prec = torch.mm(hb, ht) + cov_obs
    norm_innov = chol_solve(innov_prec, innov).t()
    k_dist = torch.mm(cov_back, ht)
    inc_ana = torch.mm(k_dist, norm_innov).squeeze(-1)
    return inc_ana


class SEKFCorr(FilterAssimilation):
    def __init__(self, b_matrix, h_jacob, smoother=True, gpu=False,
                 pre_transform=None, post_transform=None, **kwargs):
        super().__init__(
            smoother=smoother, gpu=gpu, pre_transform=pre_transform,
            post_transform=post_transform
        )
        self._b_matrix = None
        self._h_jacob = None
        self.b_matrix = b_matrix
        self.h_jacob = h_jacob
        self._func_inc = estimate_inc_corr

    @staticmethod
    def get_grid_names(state):
        grid_variable = state['grid'].variable
        if grid_variable.level_names is None:
            raise ValueError('Cannot use the SEKF with an one-dimensional '
                             'grid!')
        else:
            return grid_variable.level_names

    def _prepare_sekf(self, state, observations, pseudo_state, ):
        logger.info('Average state over ensemble')
        state_det = state.mean('ensemble')
        pseudo_state_det = pseudo_state.mean('ensemble')

        pseudo_obs, obs_state, obs_cov, obs_grid = self._prepare_obs_space(
            pseudo_state_det, observations
        )

        logger.info('Reshaping grid in state')
        grid_names = self.get_grid_names(state_det)
        state_regridded = state_det.unstack('grid').stack(hgrid=grid_names[:-1])

        return pseudo_obs, obs_state, obs_cov, obs_grid, state_regridded, \
               grid_names

    def _localize_states(self, pseudo_obs, obs_state, obs_cov, obs_grid,
                         work_state, grid_point):
        tmp_state = work_state.sel(hgrid=grid_point)
        obs_to_use = np.all(obs_grid == grid_point, axis=1)
        tmp_obs_cov = self._localize_obs_cov(obs_cov, obs_to_use)
        tmp_pseudo_obs = pseudo_obs.isel(obs_id=obs_to_use)
        tmp_obs_state = obs_state[obs_to_use]
        return tmp_pseudo_obs, tmp_obs_state, tmp_obs_cov, tmp_state

    @staticmethod
    def _localize_obs_cov(obs_cov, obs_to_use):
        return obs_cov[obs_to_use][:, obs_to_use]

    def estimate_h_jacob(self, state, pseudo_obs):
        if callable(self.h_jacob):
            eval_h_jacob = self.h_jacob(state, pseudo_obs)
        else:
            eval_h_jacob = self.h_jacob
        return eval_h_jacob

    def estimate_b_matrix(self, state, pseudo_obs):
        if callable(self.b_matrix):
            eval_b_matrix = self.b_matrix(state, pseudo_obs)
        else:
            eval_b_matrix = self.b_matrix
        return eval_b_matrix

    @staticmethod
    def _ana_incs_to_state(ana_incs, state_regrid, grid_names):
        add_dims = state_regrid.ndim-2
        new_dims = [np.newaxis, ] * add_dims + [slice(None), slice(None)]
        ana_incs = ana_incs[tuple(new_dims)]
        state_regrid[:] = ana_incs
        state_regrid = state_regrid.unstack('hgrid').stack(grid=grid_names)
        return state_regrid

    def update_state(self, state, observations, pseudo_state, analysis_time):
        (
            pseudo_obs,
            obs_state,
            obs_cov,
            obs_grid,
            work_state,
            grid_names,
        ) = self._prepare_sekf(state, observations, pseudo_state)

        ana_incs = []
        for grid_point in work_state.hgrid.values:
            (
                tmp_pseudo_obs,
                tmp_obs_state,
                tmp_obs_cov,
                tmp_state,
            ) = self._localize_states(pseudo_obs, obs_state, obs_cov, obs_grid,
                                      work_state, grid_point)
            tmp_h_jacob = self.estimate_h_jacob(tmp_state, tmp_pseudo_obs)
            tmp_b_mat = self.estimate_b_matrix(tmp_state, tmp_pseudo_obs)
            tmp_innov = self._estimate_departure(tmp_pseudo_obs, tmp_obs_state)
            tmp_states = self._states_to_torch(
                tmp_innov.values, tmp_h_jacob, tmp_b_mat, tmp_obs_cov
            )
            tmp_inc = self._func_inc(*tmp_states)
            ana_incs.append(tmp_inc.detach().numpy())
        ana_incs = np.stack(ana_incs, axis=-1)
        ana_incs = self._ana_incs_to_state(ana_incs, work_state, grid_names)
        analysis = state + ana_incs
        return analysis


class SEKFUncorr(SEKFCorr):
    def __init__(self, b_matrix, h_jacob, smoother=True, gpu=False,
                 pre_transform=None, post_transform=None, **kwargs):
        super().__init__(
            b_matrix=b_matrix, h_jacob=h_jacob,
            smoother=smoother, gpu=gpu, pre_transform=pre_transform,
            post_transform=post_transform, **kwargs
        )
        self._func_inc = estimate_inc_uncorr
        self._correlated = False

    @staticmethod
    def _localize_obs_cov(obs_cov, obs_to_use):
        return obs_cov[obs_to_use]
