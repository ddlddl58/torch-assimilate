#!/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 27.08.20

Created for torch-assimilate

@author: Tobias Sebastian Finn, tobias.sebastian.finn@uni-hamburg.de

    Copyright (C) {2020}  {Tobias Sebastian Finn}

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
import time

# External modules
import torch
import torch.nn
from torch.autograd import grad

# Internal modules
from pytassim.kernels.rbf import RBFKernel, GaussKernel
from pytassim.kernels.utils import euclidean_dist, distance_matrix


logging.basicConfig(level=logging.DEBUG)

BASE_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATA_PATH = os.path.join(os.path.dirname(BASE_PATH), 'data')


class TestGaussKernel(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = GaussKernel()
        self.tensor = torch.zeros(10, 2).normal_()

    def test_euc_dist_works(self):
        dist = self.tensor.view(10, 2, 1)-self.tensor[:3].t().view(1, 2, 3)
        euc_dist = dist.pow(2).sum(dim=1)
        ret_dist = euclidean_dist(self.tensor, self.tensor[:3])
        torch.testing.assert_allclose(ret_dist, euc_dist)

    def test_euc_dist_works_multidim(self):
        test_tensor = torch.zeros(5, 5, 10, 2).normal_()
        test_tensor_2 = torch.zeros(5, 5, 10, 2).normal_()
        un_tensor = test_tensor.unsqueeze(-2)
        un_tensor_2 = test_tensor_2.unsqueeze(-3)
        dist = un_tensor - un_tensor_2
        euc_dist = dist.pow(2).sum(dim=-1)
        ret_dist = euclidean_dist(test_tensor, test_tensor_2)
        torch.testing.assert_allclose(ret_dist, euc_dist)

    def test_gauss_kernel_works(self):
        dist = self.tensor.view(10, 2, 1)-self.tensor[:3].t().view(1, 2, 3)
        dist = dist
        factor = -0.5 * dist.pow(2).sum(dim=1)
        k_mat = torch.exp(factor)

        ret_k_mat = self.kernel(self.tensor, self.tensor[:3])
        torch.testing.assert_allclose(ret_k_mat, k_mat)

    def test_gauss_kernel_works_multidim(self):
        test_tensor = torch.zeros(5, 5, 10, 2).normal_()
        test_tensor_2 = torch.zeros(5, 5, 10, 2).normal_()

        un_tensor = test_tensor.unsqueeze(-2)
        un_tensor_2 = test_tensor_2.unsqueeze(-3)
        dist = un_tensor - un_tensor_2
        euc_dist = dist.pow(2).sum(dim=-1)
        k_mat = torch.exp(-0.5*euc_dist)

        ret_k_mat = self.kernel(test_tensor, test_tensor_2)
        torch.testing.assert_allclose(ret_k_mat, k_mat)

    def test_kernel_multidim_lengthscale(self):
        lengthscale = torch.tensor([1., 2.])
        scaled_tensor = self.tensor / lengthscale
        k_mat = self.kernel(scaled_tensor, scaled_tensor)
        self.kernel.lengthscale = lengthscale
        ret_k_mat = self.kernel(self.tensor, self.tensor)
        torch.testing.assert_allclose(ret_k_mat, k_mat)

    def test_kernel_diffbar(self):
        self.kernel.lengthscale = torch.nn.Parameter(torch.tensor([0.5]))
        k_mat = self.kernel(self.tensor, self.tensor).mean()
        right_grad = grad([k_mat], [self.kernel.lengthscale],
                          retain_graph=True)[0]
        k_mat.backward()
        torch.testing.assert_allclose(self.kernel.lengthscale.grad, right_grad)


class TestRBFKernel(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = RBFKernel()
        self.tensor = torch.zeros(10, 2).normal_()

    def test_rbf_kernel_gives_same_result_as_gauss_kernel(self):
        gauss_kernel = GaussKernel()
        right_k_mat = gauss_kernel(self.tensor, self.tensor)
        ret_k_mat = self.kernel(self.tensor, self.tensor)
        torch.testing.assert_allclose(ret_k_mat, right_k_mat)

    def test_lengthscale_returns_gamma_lengthscale(self):
        self.kernel.gamma = torch.tensor(0.1)
        self.assertEqual(
            self.kernel._get_lengthscale(),
            (0.5/torch.tensor(0.1)).sqrt()
        )





if __name__ == '__main__':
    unittest.main()
