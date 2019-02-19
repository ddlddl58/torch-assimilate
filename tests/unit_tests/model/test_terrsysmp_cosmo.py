#!/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 2/19/19

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
from unittest.mock import patch

# External modules
import xarray as xr
import numpy as np

# Internal modules
from pytassim.model.terrsysmp import cosmo


logging.basicConfig(level=logging.DEBUG)

BASE_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATA_PATH = '/scratch/local1/Data/phd_thesis/test_data'


@unittest.skipIf(
    not os.path.isdir(DATA_PATH), 'Data for TerrSysMP not available!'
)
class TestTerrSysMPCosmo(unittest.TestCase):
    def setUp(self):
        self.dataset = xr.open_dataset(
            os.path.join(DATA_PATH, 'lffd20150731060000.nc')
        ).load()
        self.assim_vars = ['T', 'W', 'W_SO', 'T_2M', 'T_S', 'U', 'U_10M',
                           'ASOB_T']

    def test_dataset_can_be_reconstructed(self):
        pre_arr = cosmo.preprocess_cosmo(self.dataset, self.assim_vars)
        post_ds = cosmo.postprocess_cosmo(pre_arr, self.dataset)
        xr.testing.assert_identical(post_ds, self.dataset)

    def test_preprocess_selects_only_available_vars(self):
        with self.assertLogs(level=logging.WARNING) as log:
            ens_arr = cosmo.preprocess_cosmo(self.dataset,
                                             self.assim_vars+['TEMP'])
        self.assertListEqual(list(ens_arr.var_name), self.assim_vars)

    def test_preprocess_raises_logger_warning_for_filtered_vars(self):
        with self.assertLogs(level=logging.WARNING) as log:
            _ = cosmo.preprocess_cosmo(
                self.dataset, self.assim_vars+['TEMP']
            )
        with self.assertRaises(AssertionError):
            with self.assertLogs(level=logging.WARNING):
                _ = cosmo.preprocess_cosmo(
                    self.dataset, self.assim_vars
                )

    def test_prepare_vgrid_sets_levels(self):
        vcoord = self.dataset['vcoord']
        ds = self.dataset[self.assim_vars]
        ret_ds = cosmo._prepare_vgrid(ds, vcoord)
        right_soil1 = ds['soil1'].values*(-1)
        right_level1 = vcoord.values
        right_level = (vcoord.values+np.roll(vcoord.values, 1))[1:] / 2
        np.testing.assert_equal(ret_ds['soil1'].values, right_soil1)
        np.testing.assert_equal(ret_ds['level1'].values, right_level1)
        np.testing.assert_equal(ret_ds['level'].values, right_level)

    def test_prepare_vgrid_sets_vcoord_if_no_soil(self):
        self.assim_vars.remove('W_SO')
        vcoord = self.dataset['vcoord']
        ds = self.dataset[['T', 'W']]
        ret_ds = cosmo._prepare_vgrid(ds, vcoord)
        np.testing.assert_equal(ret_ds['vgrid'], vcoord.values)

    def test_prepare_vgrid_sets_concatenated_if_soil(self):
        vcoord = self.dataset['vcoord']
        ds = self.dataset[self.assim_vars]
        ret_ds = cosmo._prepare_vgrid(ds, vcoord)
        soil1 = self.dataset['soil1'] * (-1)
        right_vgrid = np.concatenate([vcoord.values, soil1.values], axis=0)
        np.testing.assert_equal(ret_ds['vgrid'], right_vgrid)

    def test_precosmo_calls_prepare_vgrid(self):
        vcoord = self.dataset['vcoord']
        ds = self.dataset[self.assim_vars]
        ret_ds = cosmo._prepare_vgrid(ds, vcoord)
        with patch('pytassim.model.terrsysmp.cosmo._prepare_vgrid',
                   return_value=ret_ds) as vgrid_patch:
            _ = cosmo.preprocess_cosmo(self.dataset, self.assim_vars)
        vgrid_patch.assert_called_once()
        self.assertEqual(len(vgrid_patch.call_args[0]), 2)
        xr.testing.assert_identical(vgrid_patch.call_args[0][0], ds)
        xr.testing.assert_identical(vgrid_patch.call_args[0][1], vcoord)

    def test_expand_no_grid_vars(self):
        vcoord = self.dataset['vcoord']
        ds = self.dataset[self.assim_vars]
        prep_ds = cosmo._prepare_vgrid(ds, vcoord)
        ret_ds = cosmo._expand_vgrid(prep_ds)
        self.assertTupleEqual(
            tuple(ret_ds['T_S'].dims), ('time', 'no_vgrid', 'rlat', 'rlon')
        )
        np.testing.assert_equal(ret_ds.no_vgrid.values, np.array(0))

    def test_expand_no_grid_vars_works_with_no_vars(self):
        vcoord = self.dataset['vcoord']
        ds = self.dataset[self.assim_vars]
        prep_ds = cosmo._prepare_vgrid(ds, vcoord)
        del prep_ds['T_S']
        ret_ds = cosmo._expand_vgrid(prep_ds)

    def test_interp_remaps_to_right_vcoords(self):
        vcoord = self.dataset['vcoord']
        ds = self.dataset[self.assim_vars]
        prep_ds = cosmo._prepare_vgrid(ds, vcoord)
        reindexed_ds = cosmo._interp_vgrid(prep_ds)
        expected_values = {
            'no_vgrid': ('T_S', np.array(0)),
            'height_2m': ('T_2M', np.array(0)),
            'height_10m': ('U_10M', np.array(20)),
            'height_toa': ('ASOB_T', reindexed_ds.vgrid.values[0]),
            'soil1': ('W_SO', reindexed_ds.vgrid.values[-8:]),
            'level1': ('W', reindexed_ds.vgrid.values[:51]),
            'level': ('T', reindexed_ds.vgrid.values[:50])
        }
        for coord, val in expected_values.items():
            dropped_arr = reindexed_ds[val[0]].dropna(coord, how='all')
            np.testing.assert_equal(dropped_arr[coord].values, val[1])

    def test_precosmo_calls_interp_vgrid(self):
        vcoord = self.dataset['vcoord']
        ds = self.dataset[self.assim_vars]
        prep_ds = cosmo._prepare_vgrid(ds, vcoord)
        reindexed_ds = cosmo._interp_vgrid(prep_ds)
        with patch('pytassim.model.terrsysmp.cosmo._interp_vgrid',
                   return_value=reindexed_ds) as vgrid_patch:
            _ = cosmo.preprocess_cosmo(self.dataset, self.assim_vars)
        vgrid_patch.assert_called_once()
        self.assertEqual(len(vgrid_patch.call_args[0]), 1)
        xr.testing.assert_identical(vgrid_patch.call_args[0][0], prep_ds)

    def test_replace_coords_replaces_vertical_coords_with_vgrid(self):
        vcoord = self.dataset['vcoord']
        ds = self.dataset[self.assim_vars]
        prep_ds = cosmo._prepare_vgrid(ds, vcoord)
        reindexed_ds = cosmo._interp_vgrid(prep_ds)
        replaced = cosmo._replace_coords(reindexed_ds)
        for var in self.assim_vars:
            self.assertIn('vgrid', replaced[var].dims)

    def test_replace_coords_to_nearest_arakawa_a_grid(self):
        vcoord = self.dataset['vcoord']
        ds = self.dataset[self.assim_vars]
        prep_ds = cosmo._prepare_vgrid(ds, vcoord)
        reindexed_ds = cosmo._interp_vgrid(prep_ds)
        replaced = cosmo._replace_coords(reindexed_ds)
        self.assertNotIn('srlon', replaced['U'].dims)

    def test_precosmo_calls_replace_coords(self):
        vcoord = self.dataset['vcoord']
        ds = self.dataset[self.assim_vars]
        prep_ds = cosmo._prepare_vgrid(ds, vcoord)
        reindexed_ds = cosmo._interp_vgrid(prep_ds)
        replaced_ds = cosmo._replace_coords(reindexed_ds)
        with patch('pytassim.model.terrsysmp.cosmo._replace_coords',
                   return_value=replaced_ds) as vgrid_patch:
            _ = cosmo.preprocess_cosmo(self.dataset, self.assim_vars)
        vgrid_patch.assert_called_once()
        self.assertEqual(len(vgrid_patch.call_args[0]), 1)
        xr.testing.assert_identical(vgrid_patch.call_args[0][0], reindexed_ds)

    def test_precosmo_makes_ds_to_array(self):
        preprocessed = cosmo.preprocess_cosmo(self.dataset, self.assim_vars)
        self.assertIsInstance(preprocessed, xr.DataArray)
        self.assertIn('var_name', preprocessed.dims)
        self.assertListEqual(list(preprocessed.var_name), self.assim_vars)

    def test_precosmo_stacks_grid_coordinates(self):
        preprocessed = cosmo.preprocess_cosmo(self.dataset, self.assim_vars)
        self.assertIn('grid', preprocessed.dims)
        self.assertListEqual(list(preprocessed.indexes['grid'].names),
                             ['rlat', 'rlon', 'vgrid'])

    def test_precosmo_expands_ensemble(self):
        self.assertNotIn('ensemble', self.dataset)
        preprocessed = cosmo.preprocess_cosmo(self.dataset, self.assim_vars)
        self.assertIn('ensemble', preprocessed.dims)
        np.testing.assert_equal(preprocessed.ensemble.values, np.array(0))

    def test_precosmo_tranposes_for_valid_state(self):
        preprocessed = cosmo.preprocess_cosmo(self.dataset, self.assim_vars)
        self.assertTrue(preprocessed.state.valid)


if __name__ == '__main__':
    unittest.main()
