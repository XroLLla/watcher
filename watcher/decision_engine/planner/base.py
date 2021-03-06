# -*- encoding: utf-8 -*-
# Copyright (c) 2015 b<>com
#
# Authors: Jean-Emile DARTOIS <jean-emile.dartois@b-com.com>
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
#

"""
The :ref:`Watcher Planner <watcher_planner_definition>` is part of the
:ref:`Watcher Decision Engine <watcher_decision_engine_definition>`.

This module takes the set of :ref:`Actions <action_definition>` generated by a
:ref:`Strategy <strategy_definition>` and builds the design of a workflow which
defines how-to schedule in time those different
:ref:`Actions <action_definition>` and for each
:ref:`Action <action_definition>` what are the prerequisite conditions.

It is important to schedule :ref:`Actions <action_definition>` in time in order
to prevent overload of the :ref:`Cluster <cluster_definition>` while applying
the :ref:`Action Plan <action_plan_definition>`. For example, it is important
not to migrate too many instances at the same time in order to avoid a network
congestion which may decrease the :ref:`SLA <sla_definition>` for
:ref:`Customers <customer_definition>`.

It is also important to schedule :ref:`Actions <action_definition>` in order to
avoid security issues such as denial of service on core OpenStack services.

See :doc:`../architecture` for more details on this component.
"""

import abc
import six


@six.add_metaclass(abc.ABCMeta)
class BasePlanner(object):
    @abc.abstractmethod
    def schedule(self, context, audit_uuid, solution):
        """The  planner receives a solution to schedule

        :param solution: the solution given by the strategy to
        :param audit_uuid: the audit uuid
        :return: ActionPlan ordered sequence of change requests
            such that all security, dependency, and performance
            requirements are met.
        """
        # example: directed acyclic graph
        raise NotImplementedError()
