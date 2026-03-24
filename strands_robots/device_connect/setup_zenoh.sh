#!/usr/bin/env bash
# Source this file to point at the deployed Zenoh cluster on ECS:
#   source strands_robots/device_connect/setup_zenoh.sh

export ZENOH_CONNECT=tcp/zenoh-nlb-2cb0b84309701828.elb.us-east-1.amazonaws.com:7447
export ZENOH_MODE=client
export DEVICE_CONNECT_ALLOW_INSECURE=true

echo "Zenoh env configured: $ZENOH_CONNECT"
