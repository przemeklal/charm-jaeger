# Jaeger Charm for Kubernetes

## Description

This charm deploys Jaeger services (Query service, Collector and Agent) and enables the administrator to use Juju relations to configure automatic transfer of tracing data between microservices and Jaeger.

## Usage

### Dependencies

This charm requires ElasticSearch datastore to operate. Ensure that [elasticsearch-k8s charm](https://charmhub.io/elasticsearch-k8s) is deployed, e.g.
```
sudo sysctl -w vm.max_map_count=262144 # ES requirement, should be executed on your K8s node
juju deploy elasticsearch-k8s
```

### Build and deploy

Build and deploy the charm:
```
charmcraft pack
juju deploy ./jaeger.charm --resource agent-image=jaegertracing/jaeger-agent:1.22 \
                           --resource collector-image=jaegertracing/jaeger-collector:1.22 \
                           --resource query-image=jaegertracing/jaeger-query:1.22
```

Add relation between `jaeger` and `elasticsearch-k8s`:
```
juju add-relation jaeger elasticsearch-k8s
```

Relate with a Jaeger client application of your choice. Example charms that support relation with this charm include:
- [cnb-operator](https://github.com/mmanciop/cnb-operator)
- [charm-jaeger-hotrod](https://github.com/przemeklal/charm-jaeger-hotrod)

Example:
```
juju add-relation jaeger jaeger-hotrod
```

### Configuration options

```
  span-storage-type:
    default: elasticsearch
    description: Storage backend.
    type: string
  agent-port:
    default: 6831
    description: Jaeger agent port (used to listen for jaeger.thrift in compact Thrift protocol used by most current Jaeger clients).
    type: int
```
>Note: `elasticsearch` is the only supported datastore at the moment.
## Developing

Create and activate a virtualenv with the development requirements:

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

    ./run_tests
