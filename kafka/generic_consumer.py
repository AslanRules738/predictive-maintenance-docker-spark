"""
Test consumer

python kafka/generic_consumer.py localhost:9092 engine_cycles
"""

import argparse
from kafka import KafkaConsumer
from datetime import datetime
import sys

def main(broker, topic):
    """Main function that consumes a single message from a Kafka topic and exits.

    Args:
        broker (str): Broker in host:port format.
        topic (str): Topic to listen on.
    """
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=broker,
        auto_offset_reset='latest',  # Ensure we get new messages
        enable_auto_commit=True
    )
    
    print("Consumer initialized and waiting for message...")
    
    # Get the first message and exit
    for msg in consumer:
        print("We received the alert: {}: {}".format(datetime.now(), msg.value))
        consumer.close()
        sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("broker", help="host:port of the kafka broker.")
    parser.add_argument("topic", help="Kafka topic to post orders to.")

    args = parser.parse_args()

    print("Listening on: Broker={}, Topic={}".format(args.broker, args.topic))

    main(args.broker, args.topic)