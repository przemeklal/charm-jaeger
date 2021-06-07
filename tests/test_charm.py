# Copyright 2021 Przemysław Lal
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest

from charm import JaegerCharm
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(JaegerCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
