# -*- encoding: utf-8 -*-
#
# Copyright 2013 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Starter script for the Decision Engine manager service."""

import os
import sys

from oslo_config import cfg
from oslo_log import log as logging
from oslo_reports import guru_meditation_report as gmr
from oslo_service import service

from watcher._i18n import _LI
from watcher.common import context
from watcher.common import service as watcher_service
from watcher.decision_engine import manager
from watcher.decision_engine import sync
from watcher.decision_engine.audit import default as audit_default
from watcher import version

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def main():
    watcher_service.prepare_service(sys.argv)
    gmr.TextGuruMeditation.setup_autorun(version)

    LOG.info(_LI('Starting Watcher Decision Engine service in PID %s'),
             os.getpid())

    syncer = sync.Syncer()
    syncer.sync()

    de_service = watcher_service.Service(manager.DecisionEngineManager)

    periodic_audit = audit_default.PeriodicAuditHandler(de_service)
    launcher = service.launch(CONF, de_service)
    de_service.tg.add_dynamic_timer(
        periodic_audit.run_periodic_tasks,
        periodic_interval_max=CONF.periodic_interval,
        context=context.RequestContext(is_admin=True))
    launcher.wait()
