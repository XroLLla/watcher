# -*- encoding: utf-8 -*-
# Copyright (c) 2015 Intel Corp
#
# Authors: Junjie-Huang <junjie.huang@intel.com>
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
*Good Thermal Strategy*:

Towards to software defined infrastructure, the power and thermal
intelligences is being adopted to optimize workload, which can help
improve efficiency, reduce power, as well as to improve datacenter PUE
and lower down operation cost in data center.
Outlet (Exhaust Air) Temperature is one of the important thermal
telemetries to measure thermal/workload status of server.
"""

from oslo_log import log

from watcher._i18n import _LE
from watcher.common import exception as wexc
from watcher.decision_engine.model import resource
from watcher.decision_engine.model import vm_state
from watcher.decision_engine.strategy.strategies import base
from watcher.metrics_engine.cluster_history import ceilometer as ceil


LOG = log.getLogger(__name__)


class OutletTempControl(base.BaseStrategy):
    """[PoC] Outlet temperature control using live migration

    *Description*

    It is a migration strategy based on the outlet temperature of compute
    hosts. It generates solutions to move a workload whenever a server's
    outlet temperature is higher than the specified threshold.

    *Requirements*

    * Hardware: All computer hosts should support IPMI and PTAS technology
    * Software: Ceilometer component ceilometer-agent-ipmi running
      in each compute host, and Ceilometer API can report such telemetry
      ``hardware.ipmi.node.outlet_temperature`` successfully.
    * You must have at least 2 physical compute hosts to run this strategy.

    *Limitations*

    - This is a proof of concept that is not meant to be used in production
    - We cannot forecast how many servers should be migrated. This is the
      reason why we only plan a single virtual machine migration at a time.
      So it's better to use this algorithm with `CONTINUOUS` audits.
    - It assume that live migrations are possible

    *Spec URL*

    https://github.com/openstack/watcher-specs/blob/master/specs/mitaka/approved/outlet-temperature-based-strategy.rst
    """  # noqa

    DEFAULT_NAME = "outlet_temp_control"
    DEFAULT_DESCRIPTION = "outlet temperature based migration strategy"
    # The meter to report outlet temperature in ceilometer
    METER_NAME = "hardware.ipmi.node.outlet_temperature"
    # Unit: degree C
    THRESHOLD = 35.0

    MIGRATION = "migrate"

    def __init__(self, name=DEFAULT_NAME, description=DEFAULT_DESCRIPTION,
                 osc=None):
        """Outlet temperature control using live migration

        :param name: the name of the strategy
        :param description: a description of the strategy
        :param osc: an OpenStackClients object
        """
        super(OutletTempControl, self).__init__(name, description, osc)
        # the migration plan will be triggered when the outlet temperature
        # reaches threshold
        # TODO(zhenzanz): Threshold should be configurable for each audit
        self.threshold = self.THRESHOLD
        self._meter = self.METER_NAME
        self._ceilometer = None

    @property
    def ceilometer(self):
        if self._ceilometer is None:
            self._ceilometer = ceil.CeilometerClusterHistory(osc=self.osc)
        return self._ceilometer

    @ceilometer.setter
    def ceilometer(self, c):
        self._ceilometer = c

    def calc_used_res(self, cluster_data_model, hypervisor, cpu_capacity,
                      memory_capacity, disk_capacity):
        '''calculate the used vcpus, memory and disk based on VM flavors'''
        vms = cluster_data_model.get_mapping().get_node_vms(hypervisor)
        vcpus_used = 0
        memory_mb_used = 0
        disk_gb_used = 0
        if len(vms) > 0:
            for vm_id in vms:
                vm = cluster_data_model.get_vm_from_id(vm_id)
                vcpus_used += cpu_capacity.get_capacity(vm)
                memory_mb_used += memory_capacity.get_capacity(vm)
                disk_gb_used += disk_capacity.get_capacity(vm)

        return vcpus_used, memory_mb_used, disk_gb_used

    def group_hosts_by_outlet_temp(self, cluster_data_model):
        """Group hosts based on outlet temp meters"""

        hypervisors = cluster_data_model.get_all_hypervisors()
        size_cluster = len(hypervisors)
        if size_cluster == 0:
            raise wexc.ClusterEmpty()

        hosts_need_release = []
        hosts_target = []
        for hypervisor_id in hypervisors:
            hypervisor = cluster_data_model.get_hypervisor_from_id(
                hypervisor_id)
            resource_id = hypervisor.uuid

            outlet_temp = self.ceilometer.statistic_aggregation(
                resource_id=resource_id,
                meter_name=self._meter,
                period="30",
                aggregate='avg')
            # some hosts may not have outlet temp meters, remove from target
            if outlet_temp is None:
                LOG.warning(_LE("%s: no outlet temp data"), resource_id)
                continue

            LOG.debug("%s: outlet temperature %f" % (resource_id, outlet_temp))
            hvmap = {'hv': hypervisor, 'outlet_temp': outlet_temp}
            if outlet_temp >= self.threshold:
                # mark the hypervisor to release resources
                hosts_need_release.append(hvmap)
            else:
                hosts_target.append(hvmap)
        return hosts_need_release, hosts_target

    def choose_vm_to_migrate(self, cluster_data_model, hosts):
        """pick up an active vm instance to migrate from provided hosts"""

        for hvmap in hosts:
            mig_src_hypervisor = hvmap['hv']
            vms_of_src = cluster_data_model.get_mapping().get_node_vms(
                mig_src_hypervisor)
            if len(vms_of_src) > 0:
                for vm_id in vms_of_src:
                    try:
                        # select the first active VM to migrate
                        vm = cluster_data_model.get_vm_from_id(vm_id)
                        if vm.state != vm_state.VMState.ACTIVE.value:
                            LOG.info(_LE("VM not active, skipped: %s"),
                                     vm.uuid)
                            continue
                        return mig_src_hypervisor, vm
                    except wexc.InstanceNotFound as e:
                        LOG.info("VM not found Error: %s" % e.message)
                        pass

        return None

    def filter_dest_servers(self, cluster_data_model, hosts, vm_to_migrate):
        """Only return hosts with sufficient available resources"""

        cpu_capacity = cluster_data_model.get_resource_from_id(
            resource.ResourceType.cpu_cores)
        disk_capacity = cluster_data_model.get_resource_from_id(
            resource.ResourceType.disk)
        memory_capacity = cluster_data_model.get_resource_from_id(
            resource.ResourceType.memory)

        required_cores = cpu_capacity.get_capacity(vm_to_migrate)
        required_disk = disk_capacity.get_capacity(vm_to_migrate)
        required_memory = memory_capacity.get_capacity(vm_to_migrate)

        # filter hypervisors without enough resource
        dest_servers = []
        for hvmap in hosts:
            host = hvmap['hv']
            # available
            cores_used, mem_used, disk_used = self.calc_used_res(
                cluster_data_model, host, cpu_capacity, memory_capacity,
                disk_capacity)
            cores_available = cpu_capacity.get_capacity(host) - cores_used
            disk_available = disk_capacity.get_capacity(host) - mem_used
            mem_available = memory_capacity.get_capacity(host) - disk_used
            if cores_available >= required_cores \
                    and disk_available >= required_disk \
                    and mem_available >= required_memory:
                dest_servers.append(hvmap)

        return dest_servers

    def execute(self, original_model):
        LOG.debug("Initializing Outlet temperature strategy")

        if original_model is None:
            raise wexc.ClusterStateNotDefined()

        current_model = original_model
        hosts_need_release, hosts_target = self.group_hosts_by_outlet_temp(
            current_model)

        if len(hosts_need_release) == 0:
            # TODO(zhenzanz): return something right if there's no hot servers
            LOG.debug("No hosts require optimization")
            return self.solution

        if len(hosts_target) == 0:
            LOG.warning(_LE("No hosts under outlet temp threshold found"))
            return self.solution

        # choose the server with highest outlet t
        hosts_need_release = sorted(hosts_need_release,
                                    reverse=True,
                                    key=lambda x: (x["outlet_temp"]))

        vm_to_migrate = self.choose_vm_to_migrate(current_model,
                                                  hosts_need_release)
        # calculate the vm's cpu cores,memory,disk needs
        if vm_to_migrate is None:
            return self.solution

        mig_src_hypervisor, vm_src = vm_to_migrate
        dest_servers = self.filter_dest_servers(current_model,
                                                hosts_target,
                                                vm_src)
        # sort the filtered result by outlet temp
        # pick up the lowest one as dest server
        if len(dest_servers) == 0:
            # TODO(zhenzanz): maybe to warn that there's no resource
            # for instance.
            LOG.info(_LE("No proper target host could be found"))
            return self.solution

        dest_servers = sorted(dest_servers, key=lambda x: (x["outlet_temp"]))
        # always use the host with lowerest outlet temperature
        mig_dst_hypervisor = dest_servers[0]['hv']
        # generate solution to migrate the vm to the dest server,
        if current_model.get_mapping().migrate_vm(vm_src,
                                                  mig_src_hypervisor,
                                                  mig_dst_hypervisor):
            parameters = {'migration_type': 'live',
                          'src_hypervisor': mig_src_hypervisor.uuid,
                          'dst_hypervisor': mig_dst_hypervisor.uuid}
            self.solution.add_action(action_type=self.MIGRATION,
                                     resource_id=vm_src.uuid,
                                     input_parameters=parameters)

        self.solution.model = current_model

        return self.solution
