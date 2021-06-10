#!/usr/bin/env python3
# Copyright 2021 Przemysław Lal
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, Relation

logger = logging.getLogger(__name__)


class JaegerCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.agent_pebble_ready, self._on_agent_pebble_ready)
        self.framework.observe(self.on.collector_pebble_ready, self._on_collector_pebble_ready)
        self.framework.observe(self.on.query_pebble_ready, self._on_query_pebble_ready)

        self.framework.observe(self.on.config_changed, self._on_config_changed)

        self.framework.observe(self.on["datastore"].relation_changed,
                               self._update_datastore_relation)
        self.framework.observe(self.on["datastore"].relation_broken,
                               self._update_datastore_relation)

        self.framework.observe(self.on["distributed-tracing"].relation_joined,
                               self._update_distributed_tracing_relation)
        self.framework.observe(self.on["distributed-tracing"].relation_changed,
                               self._update_distributed_tracing_relation)

        self.framework.observe(self.on.restart_action, self._on_restart_action)

    @property
    def datastore_relation(self) -> Relation:
        # only one relation to datastore is needed/supported
        for datastore_relation in self.framework.model.relations["datastore"]:
            return datastore_relation

    @property
    def datastore_provider_unit(self) -> Relation:
        # only one relation to datastore is needed/supported
        for datastore_provider in self.datastore_relation.units:
            return datastore_provider

    @property
    def datastore_endpoint(self) -> str:
        try:
            rel_data = self.datastore_relation.data[self.datastore_provider_unit]
            hostname = rel_data.get("ingress-address")
            port = str(rel_data.get("port"))
            return "http://{}:{}".format(hostname, port)
        except (AttributeError, KeyError):
            logger.debug("no datastore endpoint present")
            return None

    def _on_agent_pebble_ready(self, event):
        self._update_agent_and_run()

    def _update_agent_and_run(self):
        self.unit.status = MaintenanceStatus('Configuring jaeger-agent')

        pebble_layer = {
            "summary": "jaeger-agent layer",
            "description": "pebble config layer for jaeger-agent",
            "services": {
                "agent": {
                    "override": "replace",
                    "summary": "jaeger-agent",
                    "command": "/go/bin/agent-linux --reporter.grpc.host-port=127.0.0.1:14250"
                               " --processor.jaeger-compact.server-host-port={}"
                               " --processor.jaeger-binary.server-host-port={}"
                               .format(str(self.model.config['agent-port']),
                                       str(self.model.config['agent-port-binary'])),
                    "startup": "enabled",
                    "environment": {},
                }
            },
        }

        container = self.unit.get_container("agent")
        container.add_layer("agent", pebble_layer, combine=True)

        if container.get_service("agent").is_running():
            container.stop("agent")
        container.start("agent")

        self.unit.status = ActiveStatus()

    def _update_collector_and_run(self):
        self.unit.status = MaintenanceStatus('Configuring jaeger-collector')

        pebble_layer = {
            "summary": "jaeger-collector layer",
            "description": "pebble config layer for jaeger-collector",
            "services": {
                "collector": {
                    "override": "replace",
                    "summary": "jaeger-collector",
                    "command": "/go/bin/collector-linux",
                    "startup": "enabled",
                    "environment": {
                        "SPAN_STORAGE_TYPE": self.model.config["span-storage-type"],
                        "ES_SERVER_URLS": self.datastore_endpoint,
                    },
                }
            },
        }

        container = self.unit.get_container("collector")
        container.add_layer("collector", pebble_layer, combine=True)

        if container.get_service("collector").is_running():
            container.stop("collector")
        container.start("collector")

        if not self.datastore_endpoint:
            self.unit.status = BlockedStatus("Datastore endpoint missing, check relations")
        else:
            self.unit.status = ActiveStatus()

    def _update_query_service_and_run(self):
        self.unit.status = MaintenanceStatus('Configuring jaeger-query')

        pebble_layer = {
            "summary": "jaeger-query layer",
            "description": "pebble config layer for jaeger-query",
            "services": {
                "query": {
                    "override": "replace",
                    "summary": "jaeger-query",
                    "command": "/go/bin/query-linux",
                    "startup": "enabled",
                    "environment": {
                        "SPAN_STORAGE_TYPE": self.model.config["span-storage-type"],
                        "ES_SERVER_URLS": self.datastore_endpoint,
                    },
                }
            },
        }

        container = self.unit.get_container("query")
        container.add_layer("query", pebble_layer, combine=True)

        if container.get_service("query").is_running():
            container.stop("query")
        container.start("query")

        if not self.datastore_endpoint:
            self.unit.status = BlockedStatus("Datastore endpoint missing, check relations")
        else:
            self.unit.status = ActiveStatus()

    def _on_collector_pebble_ready(self, event):
        self._update_collector_and_run()

    def _on_query_pebble_ready(self, event):
        self._update_query_service_and_run()

    def _on_config_changed(self, _):
        self.unit.status = MaintenanceStatus('Updating configuration')

        # update config and restart everything
        self._update_collector_and_run()
        self._update_query_service_and_run()
        self._update_agent_and_run()

        self.unit.status = ActiveStatus()

    def _update_datastore_relation(self, event):
        self.unit.status = MaintenanceStatus(
            "Updating datastore endpoint"
        )

        self._update_collector_and_run()
        self._update_query_service_and_run()

    def _update_distributed_tracing_relation(self, event):
        if self.unit.is_leader():
            event.relation.data[self.unit]['agent-address'] = \
                str(self.model.get_binding("jaeger").network.bind_address)
            event.relation.data[self.unit]['port'] = str(self.model.config['agent-port'])
            event.relation.data[self.unit]['port_binary'] = \
                str(self.model.config['agent-port-binary'])

    def _on_restart_action(self, event):
        name = event.params["service"]
        event.log("Restarting service {}".format(name))
        # note: containers and services use the same names, so it's safe to do that
        try:
            self._restart_container_service(name, name)
        except ModelError as e:
            event.fail(message=str(e))

    # workaround for https://github.com/canonical/operator/issues/491
    def _restart_container_service(self, container_name, svc_name):
        container = self.unit.get_container(container_name)
        if not container:
            msg = "Container {} not found".format(container_name)
            logger.error(msg)
            return

        if container.get_service(svc_name).is_running():
            container.stop(svc_name)
        container.start(svc_name)


if __name__ == "__main__":
    main(JaegerCharm)
