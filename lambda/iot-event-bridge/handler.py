"""
IoT Core → EventBridge bridge Lambda.
IoT topic rule invokes this function with the robot event payload.
This function puts the event onto the custom EventBridge bus.
"""
import json
import os
import boto3

events_client = boto3.client("events")
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]


def lambda_handler(event, context):
    detail_type = event.get("event_type", "RobotEvent")

    response = events_client.put_events(
        Entries=[
            {
                "Source": "robotops.robot",
                "DetailType": detail_type,
                "Detail": json.dumps(event),
                "EventBusName": EVENT_BUS_NAME,
            }
        ]
    )

    failed = response.get("FailedEntryCount", 0)
    if failed > 0:
        raise RuntimeError(f"EventBridge PutEvents failed: {response['Entries']}")

    return {"statusCode": 200, "failedEntryCount": failed}
