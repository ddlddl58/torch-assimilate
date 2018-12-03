#!/bin/env python
# -*- coding: utf-8 -*-
#
# Created on 02.12.18
#
# Created for torch-assim
#
# @author: Tobias Sebastian Finn, tobias.sebastian.finn@uni-hamburg.de
#
#    Copyright (C) {2018}  {Tobias Sebastian Finn}
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
import os
import unittest
import logging

# External modules
import torch
import numpy as np

# Internal modules
from pytassim.model.lorenz_96 import torch_roll, Lorenz96


rnd = np.random.RandomState(42)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

logging.basicConfig(level=logging.DEBUG)


class TestLorenz96(unittest.TestCase):
    def setUp(self):
        self.model = Lorenz96()
        self.state = rnd.normal(size=40)
        self.torch_state = torch.tensor(self.state)

    def test_torch_roll(self):
        rolled_array = np.roll(self.state, shift=4, axis=0)
        returned_array = torch_roll(self.torch_state, 4).numpy().copy()
        np.testing.assert_equal(returned_array, rolled_array)
        rolled_array = np.roll(self.state, shift=-4, axis=0)
        returned_array = torch_roll(self.torch_state, shift=-4).numpy().copy()
        np.testing.assert_equal(returned_array, rolled_array)

    def test_calc_forcing_returns_forcing(self):
        returned_forcing = self.model._calc_forcing(self.state)
        self.assertEqual(returned_forcing, self.model.forcing)
        self.model.forcing = 2
        returned_forcing = self.model._calc_forcing(self.state)
        self.assertEqual(returned_forcing, self.model.forcing)

    def test_calc_advection_returns_advection_term(self):
        diff = np.roll(self.state, -1) - np.roll(self.state, 2)
        right_advection = diff * np.roll(self.state, 1)
        returned_advection = self.model._calc_advection(self.torch_state)
        np.testing.assert_equal(right_advection, returned_advection.numpy())


if __name__ == '__main__':
    unittest.main()
