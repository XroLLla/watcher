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
import mock
import contextlib
from datetime import datetime

from watcher.decision_engine.audit import default as default
from watcher.decision_engine.messaging import events
from watcher.metrics_engine.cluster_model_collector import manager
from watcher.objects import audit as audit_objects
from watcher.tests.db import base
from watcher.tests.decision_engine.strategy.strategies import \
    faker_cluster_state as faker
from watcher.tests.objects import utils as obj_utils


class TestDefaultAuditHandler(base.DbTestCase):
    def setUp(self):
        super(TestDefaultAuditHandler, self).setUp()
        obj_utils.create_test_goal(self.context, id=1, name="DUMMY")
        audit_template = obj_utils.create_test_audit_template(
            self.context)
        self.audit = obj_utils.create_test_audit(
            self.context,
            audit_template_id=audit_template.id)

    @mock.patch.object(manager.CollectorManager, "get_cluster_model_collector")
    def test_trigger_audit_without_errors(self, mock_collector):
        mock_collector.return_value = faker.FakerModelCollector()
        audit_handler = default.DefaultAuditHandler(mock.MagicMock())
        audit_handler.execute(self.audit.uuid, self.context)

    @mock.patch.object(manager.CollectorManager, "get_cluster_model_collector")
    def test_trigger_audit_state_succeeded(self, mock_collector):
        mock_collector.return_value = faker.FakerModelCollector()
        audit_handler = default.DefaultAuditHandler(mock.MagicMock())
        audit_handler.execute(self.audit.uuid, self.context)
        audit = audit_objects.Audit.get_by_uuid(self.context, self.audit.uuid)
        self.assertEqual(audit_objects.State.SUCCEEDED, audit.state)

    @mock.patch.object(manager.CollectorManager, "get_cluster_model_collector")
    def test_trigger_audit_send_notification(self, mock_collector):
        messaging = mock.MagicMock()
        mock_collector.return_value = faker.FakerModelCollector()
        audit_handler = default.DefaultAuditHandler(messaging)
        audit_handler.execute(self.audit.uuid, self.context)

        call_on_going = mock.call(events.Events.TRIGGER_AUDIT.name, {
            'audit_status': audit_objects.State.ONGOING,
            'audit_uuid': self.audit.uuid})
        call_succeeded = mock.call(events.Events.TRIGGER_AUDIT.name, {
            'audit_status': audit_objects.State.SUCCEEDED,
            'audit_uuid': self.audit.uuid})

        calls = [call_on_going, call_succeeded]
        messaging.status_topic_handler.publish_event.assert_has_calls(calls)
        self.assertEqual(
            2, messaging.status_topic_handler.publish_event.call_count)

    def test_update_audit_next_launch_oneshote_type(self):
        audit_handler = default.DefaultAuditHandler(mock.MagicMock())
        audit = audit_objects.Audit.get_by_uuid(self.context, self.audit.uuid)
        prev_next_launch = audit.next_launch
        audit_handler.execute(self.audit.uuid, self.context)
        audit = audit_objects.Audit.get_by_uuid(self.context, self.audit.uuid)
        self.assertEqual(prev_next_launch, audit.next_launch)

    def test_update_audit_next_launch_continuous_type(self):
        audit_handler = default.PeriodicAuditHandler(mock.MagicMock())
        audit = audit_objects.Audit.get_by_uuid(self.context, self.audit.uuid)
        audit.type = 'CONTINUOUS'
        audit.save()
        prev_next_launch = audit.next_launch
        audit_handler.execute(self.audit.uuid, self.context)
        audit = audit_objects.Audit.get_by_uuid(self.context, self.audit.uuid)
        self.assertNotEqual(prev_next_launch, audit.next_launch)


class TestPeriodicAuditHandler(base.DbTestCase):
    def setUp(self):
        super(TestPeriodicAuditHandler, self).setUp()
        obj_utils.create_test_goal(self.context, id=1, name="DUMMY")
        audit_template = obj_utils.create_test_audit_template(
            self.context)
        self.audit = obj_utils.create_test_audit(
            self.context,
            audit_template_id=audit_template.id,
            type="CONTINUOUS")

    def test_launch_audits_periodically(self):
        audit_handler = default.PeriodicAuditHandler(mock.MagicMock())
        audits = []
        audits.append(audit_objects.Audit.get_by_uuid(self.context,
                                                      self.audit.uuid))
        with contextlib.nested(
            mock.patch.object(audit_objects.Audit, 'list',
                              return_value=audits),
            mock.patch.object(audit_handler.executor, 'submit')
                ) as (mock_list, mock_submit):
            audit_handler.launch_audits_periodically(self.context)
            mock_submit.assert_called()
