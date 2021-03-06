# -*- encoding: utf-8 -*-
# Copyright (c) 2015 b<>com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import
from __future__ import unicode_literals

import types

from mock import patch
from oslo_config import cfg
from watcher.decision_engine.manager import DecisionEngineManager
from watcher.tests.base import BaseTestCase

from watcher.cmd import decisionengine


class TestDecisionEngine(BaseTestCase):

    def setUp(self):
        super(TestDecisionEngine, self).setUp()

        self.conf = cfg.CONF
        self._parse_cli_opts = self.conf._parse_cli_opts

        def _fake_parse(self, args=[]):
            return cfg.ConfigOpts._parse_cli_opts(self, [])

        _fake_parse_method = types.MethodType(_fake_parse, self.conf)
        self.conf._parse_cli_opts = _fake_parse_method

    def tearDown(self):
        super(TestDecisionEngine, self).tearDown()
        self.conf._parse_cli_opts = self._parse_cli_opts

    @patch.object(DecisionEngineManager, "connect")
    @patch.object(DecisionEngineManager, "join")
    def test_run_de_app(self, m_connect, m_join):
        decisionengine.main()
        self.assertEqual(m_connect.call_count, 1)
        self.assertEqual(m_join.call_count, 1)
