#!/usr/bin/env bash

DIR=/shared/project

python ${DIR}/kafka/generic_consumer.py kafka:9092 engine-alert
