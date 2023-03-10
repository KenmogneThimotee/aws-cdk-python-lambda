import boto3
import os
import json
import decimal
from typing import Dict, Any

TABLE_NAME = os.environ.get("ORDER_TABLE")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return str(o)
        return super(DecimalEncoder, self).default(o)

def get_order_by_id(event):
    order_id = event['arguments']['id']
    item = table.get_item(
        Key={
            'id': order_id,
            'user_id': "demo_user"
        }
    )

    return item

def handler(event, context):
    print("event context : ", event)
    item = get_order_by_id(event)
    return item
    




