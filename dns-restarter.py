#!/usr/bin/env python3
from dotenv import load_dotenv
load_dotenv()

import docker
import time
import logging
import os
from dns import resolver, exception as dns_exception
from prometheus_client import start_http_server, Counter

TIMES_RESTARTED = Counter('times_restarted', 'number of times dnsdock was restarted')

# config
loglevel = os.environ.get('LOG_LEVEL', "info")
docker_socket = os.environ.get('DOCKER_HOST', 'unix://var/run/docker.sock')
resolvers = os.environ.get('DNS_RESOLVERS', '10.1.1.1').split(",")
dnsdock_container_name = os.environ.get('DNSDOCK_CONTAINER_NAME', "mediastation_dnsdock_1")
restart_interval = int(os.environ.get('RESTART_INTERVAL', '30'))
metrics_port = int(os.environ.get('METRICS_PORT', '9199'))

# create logger
loglevel_numerical = getattr(logging, loglevel.upper(), None)
logger = logging.getLogger(__name__)
logger.setLevel(loglevel_numerical)
ch = logging.StreamHandler()
ch.setLevel(loglevel_numerical)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# dns
res = resolver.Resolver()
res.nameservers = resolvers

# docker
client = docker.DockerClient(base_url=docker_socket)

# info
logger.info(f"Docker socket: {docker_socket}")
logger.info(f"Resolvers: {resolvers}")
logger.info(f"Restart interval (seconds): {restart_interval}")


def get_dnsdock_alias(container):
  try:
    return [env.split("=")[1] for env in container.attrs['Config']['Env'] if env.startswith("DNSDOCK_ALIAS")].pop()
  except IndexError:
    return None

def get_network_ip(container):
  try:
    networks = container.attrs['NetworkSettings']['Networks'].keys()
    for network in networks:
      return container.attrs['NetworkSettings']['Networks'][network]['IPAddress']
  except IndexError:
    return None

def main_loop():
  container_list = client.containers.list()
  dnsdock_container = [ctr for ctr in container_list if ctr.name == dnsdock_container_name].pop()
  requires_restart = False
  for container in container_list:
    alias = get_dnsdock_alias(container)
    if alias:
      container_ip = get_network_ip(container)
      resolved_address = None
      try:
        resolved_address = [ans.address for ans in res.query(alias)].pop()
      except (dns_exception.DNSException, IndexError) as e:
        logger.error(e.msg)
        logger.error(f"Couldn't resolve {alias} for {container.name} this will trigger a restart.")
        requires_restart = True
        break
      logger.debug(f"Alias detected for {container.name} as {alias} expected for {container_ip} and resolved as {resolved_address}")

  if requires_restart:
    dnsdock_container.restart()
    TIMES_RESTARTED.inc()
    logger.info("Restarted dnsdock.")


if __name__ == '__main__':
  start_http_server(metrics_port)
  logger.info("Starting loop.")
  while True:
    main_loop()
    time.sleep(restart_interval)