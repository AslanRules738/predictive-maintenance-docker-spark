#!/usr/bin/env bash

RPS=$1
DIR=/media/

echo "rps= $RPS"
python ${DIR}/kafka/engine_cycle_producer.py kafka:9092 engine-stream -s ${DIR}/data/test_x.csv -r ${RPS}
