# -*- encoding: utf-8 -*-
# Copyright (c) 2016 b<>com
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

from __future__ import unicode_literals

import uuid

from tempest import test
from tempest_lib import exceptions as lib_exc

from watcher_tempest_plugin.tests.api.admin import base


class TestCreateDeleteAuditTemplate(base.BaseInfraOptimTest):
    """Tests on audit templates"""

    @test.attr(type='smoke')
    def test_create_audit_template(self):
        params = {'name': 'my at name %s' % uuid.uuid4(),
                  'description': 'my at description',
                  'host_aggregate': 12,
                  'goal': 'DUMMY',
                  'extra': {'str': 'value', 'int': 123, 'float': 0.123,
                            'bool': True, 'list': [1, 2, 3],
                            'dict': {'foo': 'bar'}}}

        _, body = self.create_audit_template(**params)
        self.assert_expected(params, body)

        _, audit_template = self.client.show_audit_template(body['uuid'])
        self.assert_expected(audit_template, body)

    @test.attr(type='smoke')
    def test_create_audit_template_unicode_description(self):
        # Use a unicode string for testing:
        params = {'name': 'my at name %s' % uuid.uuid4(),
                  'description': 'my àt déscrïptïôn',
                  'host_aggregate': 12,
                  'goal': 'DUMMY',
                  'extra': {'foo': 'bar'}}

        _, body = self.create_audit_template(**params)
        self.assert_expected(params, body)

        _, audit_template = self.client.show_audit_template(body['uuid'])
        self.assert_expected(audit_template, body)

    @test.attr(type='smoke')
    def test_delete_audit_template(self):
        _, body = self.create_audit_template()
        audit_uuid = body['uuid']

        self.delete_audit_template(audit_uuid)

        self.assertRaises(lib_exc.NotFound, self.client.show_audit_template,
                          audit_uuid)


class TestAuditTemplate(base.BaseInfraOptimTest):
    """Tests for audit_template."""

    @classmethod
    def resource_setup(cls):
        super(TestAuditTemplate, cls).resource_setup()
        _, cls.audit_template = cls.create_audit_template()

    @test.attr(type='smoke')
    def test_show_audit_template(self):
        _, audit_template = self.client.show_audit_template(
            self.audit_template['uuid'])

        self.assert_expected(self.audit_template, audit_template)

    @test.attr(type='smoke')
    def test_filter_audit_template_by_goal(self):
        _, audit_templates = self.client.list_audit_templates(
            goal=self.audit_template['goal'])

        audit_template_uuids = [
            at["uuid"] for at in audit_templates['audit_templates']]
        self.assertIn(self.audit_template['uuid'], audit_template_uuids)

    @test.attr(type='smoke')
    def test_show_audit_template_with_links(self):
        _, audit_template = self.client.show_audit_template(
            self.audit_template['uuid'])
        self.assertIn('links', audit_template.keys())
        self.assertEqual(2, len(audit_template['links']))
        self.assertIn(audit_template['uuid'],
                      audit_template['links'][0]['href'])

    @test.attr(type="smoke")
    def test_list_audit_templates(self):
        _, body = self.client.list_audit_templates()
        self.assertIn(self.audit_template['uuid'],
                      [i['uuid'] for i in body['audit_templates']])
        # Verify self links.
        for audit_template in body['audit_templates']:
            self.validate_self_link('audit_templates', audit_template['uuid'],
                                    audit_template['links'][0]['href'])

    @test.attr(type='smoke')
    def test_list_with_limit(self):
        # We create 3 extra audit templates to exceed the limit we fix
        for _ in range(3):
            self.create_audit_template()

        _, body = self.client.list_audit_templates(limit=3)

        next_marker = body['audit_templates'][-1]['uuid']
        self.assertEqual(len(body['audit_templates']), 3)
        self.assertIn(next_marker, body['next'])

    @test.attr(type='smoke')
    def test_update_audit_template_replace(self):
        params = {'name': 'my at name %s' % uuid.uuid4(),
                  'description': 'my at description',
                  'host_aggregate': 12,
                  'goal': 'DUMMY',
                  'extra': {'key1': 'value1', 'key2': 'value2'}}

        _, body = self.create_audit_template(**params)

        new_name = 'my at new name %s' % uuid.uuid4()
        new_description = 'my new at description'
        new_host_aggregate = 10
        new_goal = 'A NEW GOAL'
        new_extra = {'key1': 'new-value1', 'key2': 'new-value2'}

        patch = [{'path': '/name',
                  'op': 'replace',
                  'value': new_name},
                 {'path': '/description',
                  'op': 'replace',
                  'value': new_description},
                 {'path': '/host_aggregate',
                  'op': 'replace',
                  'value': new_host_aggregate},
                 {'path': '/goal',
                  'op': 'replace',
                  'value': new_goal},
                 {'path': '/extra/key1',
                  'op': 'replace',
                  'value': new_extra['key1']},
                 {'path': '/extra/key2',
                  'op': 'replace',
                  'value': new_extra['key2']}]

        self.client.update_audit_template(body['uuid'], patch)

        _, body = self.client.show_audit_template(body['uuid'])
        self.assertEqual(new_name, body['name'])
        self.assertEqual(new_description, body['description'])
        self.assertEqual(new_host_aggregate, body['host_aggregate'])
        self.assertEqual(new_goal, body['goal'])
        self.assertEqual(new_extra, body['extra'])

    @test.attr(type='smoke')
    def test_update_audit_template_remove(self):
        extra = {'key1': 'value1', 'key2': 'value2', 'key3': 'value3'}
        description = 'my at description'
        goal = 'DUMMY'
        name = 'my at name %s' % uuid.uuid4()
        params = {'name': name,
                  'description': description,
                  'host_aggregate': 12,
                  'goal': goal,
                  'extra': extra}

        _, audit_template = self.create_audit_template(**params)

        # Removing one item from the collection
        self.client.update_audit_template(
            audit_template['uuid'],
            [{'path': '/extra/key2', 'op': 'remove'}])

        extra.pop('key2')
        _, body = self.client.show_audit_template(audit_template['uuid'])
        self.assertEqual(extra, body['extra'])

        # Removing the collection
        self.client.update_audit_template(
            audit_template['uuid'],
            [{'path': '/extra', 'op': 'remove'}])
        _, body = self.client.show_audit_template(audit_template['uuid'])
        self.assertEqual({}, body['extra'])

        # Removing the Host Aggregate ID
        self.client.update_audit_template(
            audit_template['uuid'],
            [{'path': '/host_aggregate', 'op': 'remove'}])
        _, body = self.client.show_audit_template(audit_template['uuid'])
        self.assertEqual({}, body['extra'])

        # Assert nothing else was changed
        self.assertEqual(name, body['name'])
        self.assertEqual(description, body['description'])
        self.assertEqual(goal, body['goal'])

    @test.attr(type='smoke')
    def test_update_audit_template_add(self):
        params = {'name': 'my at name %s' % uuid.uuid4(),
                  'description': 'my at description',
                  'host_aggregate': 12,
                  'goal': 'DUMMY'}

        _, body = self.create_audit_template(**params)

        extra = {'key1': 'value1', 'key2': 'value2'}

        patch = [{'path': '/extra/key1',
                  'op': 'add',
                  'value': extra['key1']},
                 {'path': '/extra/key2',
                  'op': 'add',
                  'value': extra['key2']}]

        self.client.update_audit_template(body['uuid'], patch)

        _, body = self.client.show_audit_template(body['uuid'])
        self.assertEqual(extra, body['extra'])
