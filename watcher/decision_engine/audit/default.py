# -*- encoding: utf-8 -*-
# Copyright (c) 2015 b<>com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from concurrent import futures

from datetime import datetime
from datetime import timedelta

from oslo_config import cfg
from oslo_log import log
from oslo_service import periodic_task

from watcher.applier import rpcapi
from watcher.common.messaging.events import event as watcher_event
from watcher.decision_engine.audit import base
from watcher.decision_engine.messaging import events as de_events
from watcher.decision_engine.planner import manager as planner_manager
from watcher.decision_engine.strategy.context import default as default_context
from watcher.objects import action_plan
from watcher.objects import audit as audit_objects


LOG = log.getLogger(__name__)
CONF = cfg.CONF


class PeriodicAuditHandler(periodic_task.PeriodicTasks):

    def __init__(self, messaging):
        super(PeriodicAuditHandler, self).__init__(CONF)
        self._messaging = messaging
        self._executor = futures.ThreadPoolExecutor(
            CONF.watcher_decision_engine.max_workers)

    @property
    def executor(self):
        return self._executor

    @property
    def messaging(self):
        return self._messaging

    def execute(self, audit_uuid, context):
        da = DefaultAuditHandler(self._messaging)
        da.execute(audit_uuid, context)
        return audit_uuid

    @periodic_task.periodic_task(run_immediately=True)
    def launch_audits_periodically(self, context):
        audits = audit_objects.Audit.list(context,
                                          filters={'type': 'CONTINUOUS'})
        completed_audits = []
        for audit in audits:
            launch_audit_at = audit.next_launch.replace(tzinfo=None)
            if datetime.utcnow() > launch_audit_at:
                completed_audits.append(self.executor.submit(self.execute,
                                                             audit.uuid,
                                                             context))

        for future in futures.as_completed(completed_audits):
            audit_uuid = future.result()
            ap_filters = {'audit_uuid': audit_uuid,
                          'state': action_plan.State.RECOMMENDED}
            action_plans = action_plan.ActionPlan.list(context,
                                                       filters=ap_filters)
            for plan in action_plans:
                applier_client = rpcapi.ApplierAPI()
                applier_client.launch_action_plan(context, plan.uuid)


class DefaultAuditHandler(base.BaseAuditHandler):
    def __init__(self, messaging):
        super(DefaultAuditHandler, self).__init__()
        self._messaging = messaging
        self._strategy_context = default_context.DefaultStrategyContext()
        self._planner_manager = planner_manager.PlannerManager()
        self._planner = None

    @property
    def planner(self):
        if self._planner is None:
            self._planner = self._planner_manager.load()
        return self._planner

    @property
    def messaging(self):
        return self._messaging

    @property
    def strategy_context(self):
        return self._strategy_context

    def notify(self, audit_uuid, event_type, status):
        event = watcher_event.Event()
        event.type = event_type
        event.data = {}
        payload = {'audit_uuid': audit_uuid,
                   'audit_status': status}
        self.messaging.status_topic_handler.publish_event(
            event.type.name, payload)

    def update_audit_state(self, request_context, audit_uuid, state):
        LOG.debug("Update audit state: %s", state)
        audit = audit_objects.Audit.get_by_uuid(request_context, audit_uuid)
        audit.state = state
        audit.save()
        self.notify(audit_uuid, de_events.Events.TRIGGER_AUDIT, state)
        return audit

    def update_audit_next_launch(self, request_context, audit_uuid):
        audit = audit_objects.Audit.get_by_uuid(request_context, audit_uuid)
        audit.next_launch = datetime.utcnow() + timedelta(seconds=audit.period)
        audit.save()
        # add notify of re-triggering
        return audit

    def execute(self, audit_uuid, request_context):
        try:
            LOG.debug("Trigger audit %s", audit_uuid)
            # change state of the audit to ONGOING
            audit = self.update_audit_state(request_context, audit_uuid,
                                            audit_objects.State.ONGOING)

            # execute the strategy
            solution = self.strategy_context.execute_strategy(audit_uuid,
                                                              request_context)

            self.planner.schedule(request_context, audit.id, solution)

            # change state of the audit to SUCCEEDED
            self.update_audit_state(request_context, audit_uuid,
                                    audit_objects.State.SUCCEEDED)
        except Exception as e:
            LOG.exception(e)
            self.update_audit_state(request_context, audit_uuid,
                                    audit_objects.State.FAILED)
        finally:
            self.update_audit_next_launch(request_context, audit_uuid)
