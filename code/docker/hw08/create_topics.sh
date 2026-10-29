#!/bin/bash
set -euo pipefail
for name in entity_requests entity_responses inbox tasks drafts final dead_letter; do
  partitions=1
  if [ "$name" = tasks ]; then partitions=2; fi
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:19092 --create --if-not-exists --topic "s6102_$name" --partitions "$partitions" --replication-factor 1
  description=$(/opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:19092 --describe --topic "s6102_$name")
  echo "$description"
  if ! echo "$description" | head -1 | grep -q "PartitionCount: $partitions"; then
    echo "Topic partition mismatch: s6102_$name" >&2
    exit 1
  fi
done
