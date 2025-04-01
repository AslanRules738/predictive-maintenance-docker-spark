import sys
import os
import argparse
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.ml.feature import RFormulaModel
from pyspark.ml.feature import MinMaxScalerModel
from pyspark.ml.regression import AFTSurvivalRegressionModel


ROOT_DIR = os.path.abspath('/media/')
MODEL_DIR = ROOT_DIR + '/aft/models/'

sys.path.append(ROOT_DIR)
import engine_util

DEFAULT_OUTPUT = 'output'


class Predictor:

    def __init__(self, model_dir, config):
        self.config = config
        self.aft_model = AFTSurvivalRegressionModel.load(model_dir+'aft')
        self.formula_model = RFormulaModel.load(model_dir+'formula')
        self.scaler_model = MinMaxScalerModel.load(model_dir+'scaler')

        self.schema, self.feature_cols, self.label_cols = engine_util.create_engine_schema()
        self.cn = engine_util.CleanData(self.schema, self.feature_cols)

    def transform_and_predict(self, df):
        """Transform and predict in one step for real-time processing"""
        df2 = df.select(F.split('value', ',').alias('value'))
        df_result = df2.select(*[df2['value'][i] for i in range(26)])

        cycles_df = self.cn.fit(df_result)
        prepared_df = self.formula_model.transform(cycles_df)
        scaled_df = self.scaler_model.transform(prepared_df)
        pred_df = self.aft_model.transform(scaled_df)

        return pred_df.select('id', 'cycle', 'prediction')


def main(broker, topic, config):
    """Main function that connects a Kafka topic to a Spark engine for real-time processing.

    Args:
        broker (str): Broker in host:port format.
        topic (str): Topic to listen on.
        config (dict): Configuration stored as name/value.
    """

    spark = SparkSession \
        .builder \
        .appName("engine-stream-consumer-realtime") \
        .master("local[*]") \
        .config("spark.streaming.kafka.consumer.cache.enabled", "false") \
        .config("spark.streaming.stopGracefullyOnShutdown", "true") \
        .config("spark.sql.streaming.minBatchesToRetain", "10") \
        .config("spark.sql.streaming.pollingDelay", "10ms") \
        .getOrCreate()

    predictor = Predictor(MODEL_DIR, config)

    # Set up the input stream with minimal processing delay
    input_stream = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", broker) \
        .option("subscribe", topic) \
        .option("startingOffsets", "latest") \
        .option("maxOffsetsPerTrigger", 1000) \
        .option("failOnDataLoss", "false") \
        .load() \
        .selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)")

    # Process each record as it arrives
    predicted_df = predictor.transform_and_predict(input_stream)
    
    # Filter for alerts based on threshold
    alert_df = predicted_df.filter(F.col('prediction') <= config['rulThreshold'])
    
    # Write alerts to Kafka
    alert_query = alert_df \
        .select(
            F.concat(
                F.col('id'), F.lit(','), F.col('cycle'), F.lit(','), 
                F.col('prediction'), F.lit(',TOPIC'), F.lit(config['topic'])
            ).alias('value')
        ) \
        .selectExpr("CAST(value AS STRING)") \
        .writeStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", config['broker']) \
        .option("topic", config['alertTopic']) \
        .option("checkpointLocation", config['outputDirectory'] + "/checkpoints/alerts") \
        .trigger(processingTime='1 second') \
        .outputMode("append") \
        .start()
    
    # Also log to console for monitoring
    console_query = predicted_df \
        .writeStream \
        .format("console") \
        .option("truncate", False) \
        .trigger(processingTime='1 second') \
        .outputMode("append") \
        .start()
    
    # Wait for termination
    spark.streams.awaitAnyTermination()
    
    spark.stop()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("broker", help="host:port of the kafka broker.")
    parser.add_argument("topic", help="Topic to monitor.", default="engine-stream")
    parser.add_argument("alertTopic", help="Topic to send alerts to.", default="engine-alert")
    parser.add_argument("-o", "--outputDirectory", help="Output directory", default=DEFAULT_OUTPUT)
    parser.add_argument("-r", "--rulThreshold", help="The predicted RUL to alert on", default=30)

    args = parser.parse_args()

    # Simplified config for real-time processing
    conf = {
        "broker": args.broker,
        "topic": args.topic,
        "alertTopic": args.alertTopic,
        "outputDirectory": args.outputDirectory,
        "rulThreshold": int(args.rulThreshold)
    }

    print("Broker={}, Monitoring Topic={}, Alert Topic={}".format(args.broker, args.topic, args.alertTopic))
    print("Configuration: ", conf)

    main(args.broker, args.topic, conf)