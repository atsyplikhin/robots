#!/usr/bin/env bash
# Source this file to point at the deployed NATS cluster on ECS:
#   source strands_robots/device_connect/setup_nats.sh

export MESSAGING_BACKEND=nats
export NATS_URL=nats://nats-nlb-6b2176379647decc.elb.us-east-1.amazonaws.com:4222
export DEVICE_CONNECT_ALLOW_INSECURE=true

echo "NATS env configured: $NATS_URL"
