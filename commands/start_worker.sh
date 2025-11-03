#!/bin/bash
set -e

echo "Starting event worker"

cd /usr/src/app
python -m workers.event_worker