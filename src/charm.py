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
from ops.model import ActiveStatus, MaintenanceStatus

logger = logging.getLogger(__name__)


class JaegerCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.agent_pebble_ready,
                               self._on_agent_pebble_ready)

        self.framework.observe(self.on.collector_pebble_ready,
                               self._on_collector_pebble_ready)

        self.framework.observe(self.on.query_pebble_ready,
                               self._on_query_pebble_ready)

        self.framework.observe(self.on.config_changed,
                               self._on_config_changed)

        self.framework.observe(self.on["datastore"].relation_changed,
                               self._on_datastore_relation_changed)

        self.framework.observe(self.on["jaeger"].relation_changed,
                               self._on_jaeger_relation_changed)

        self._stored.set_default(es_server_url=str())

    def _on_agent_pebble_ready(self, event):
        self.unit.status = MaintenanceStatus('Configuring jaeger-agent')

        pebble_layer = {
            "summary": "jaeger-agent layer",
            "description": "pebble config layer for jaeger-agent",
            "services": {
                "agent": {
                    "override": "replace",
                    "summary": "jaeger-agent",
                    "command": "/go/bin/agent-linux --reporter.grpc.host-port=127.0.0.1:14250",
                    "startup": "enabled",
                    "environment": {},
                }
            },
        }

        container = event.workload
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
                        "ES_SERVER_URLS": self._stored.es_server_url,
                    },
                }
            },
        }

        container = self.unit.get_container("collector")
        container.add_layer("collector", pebble_layer, combine=True)

        if container.get_service("collector").is_running():
            container.stop("collector")
        container.start("collector")

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
                        "ES_SERVER_URLS": self._stored.es_server_url,
                    },
                }
            },
        }

        container = self.unit.get_container("query")
        container.add_layer("query", pebble_layer, combine=True)

        if container.get_service("query").is_running():
            container.stop("query")
        container.start("query")

        self.unit.status = ActiveStatus()

    def _on_collector_pebble_ready(self, event):
        self._update_collector_and_run()

    def _on_query_pebble_ready(self, event):
        self._update_query_service_and_run()

    def _on_config_changed(self, _):
        return

    def _on_datastore_relation_changed(self, event):
        self.unit.status = MaintenanceStatus(
            "Updating datastore relation"
        )

        data = event.relation.data[event.unit]

        es_hostname = data.get("ingress-address")
        es_port = data.get("port")

        self._stored.es_server_url = "http://{}:{}".format(es_hostname, es_port)

        # restart collector and query
        self._update_collector_and_run()
        self._update_query_service_and_run()

        logger.debug("New ES endpoint received: %s", self._stored.es_server_url)

        self.unit.status = ActiveStatus()

    def _on_jaeger_relation_changed(self, event):
        if self.unit.is_leader():
            event.relation.data[self.unit]['agent-address'] = str(self.model.get_binding("jaeger").network.bind_address)
            event.relation.data[self.unit]['port'] = str(self.model.config['agent-port'])


if __name__ == "__main__":
    main(JaegerCharm)
