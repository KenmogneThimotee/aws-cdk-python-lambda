from os import path
import os
from constructs import Construct
from aws_cdk import (
    Duration,
    Stack,
    aws_iam as iam,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
)
import aws_cdk.aws_appsync as appsync
from aws_cdk import aws_lambda as lambda_



class CdkAccelerateStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        queue = sqs.Queue(
            self, "CdkAccelerateQueue",
            visibility_timeout=Duration.seconds(300),
        )

        api = appsync.CfnGraphQLApi(self, "Api", 
        name="demo",
        authentication_type="API_KEY"
        )

        data_schema = ''
        with open("../schema.graphql", 'r') as file:
            data_schema = file.read().replace('\n', '')

        schema = appsync.CfnGraphQLSchema(scope=self, id="schema", api_id=api.attr_api_id, definition=data_schema)

        lambdaDs_function = lambda_.CfnFunction(self, "MyCfnFunction",
            code=lambda_.CfnFunction.CodeProperty(
                image_uri="imageUri",
                s3_bucket="s3Bucket",
                s3_key="s3Key",
                s3_object_version="s3ObjectVersion",
                zip_file="zipFile"
            ),
            role="role",

            # the properties below are optional
            architectures=["x86_64"],
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "TABLE": "variables"
                }
            ),
            function_name="order-lambda-ds",
            handler="handler",
            package_type="zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )

        lambda_config_property = appsync.CfnDataSource.LambdaConfigProperty(
            lambda_function_arn=lambdaDs_function.attr_arn
        )
        
        lambdaDs = appsync.CfnDataSource(self, "lambda-ds", api.attr_api_id, "lambda-ds", type="AWS_LAMBDA",
        lambda_config=lambda_config_property)

        list_orders = appsync.CfnResolver(self, "list-orders",
        api_id=api.attr_api_id,
        field_name="orders",
        type_name="query")

        get_order = appsync.CfnResolver(self, "get-order",
        api_id=api.attr_api_id,
        field_name="order",
        type_name="query")

        post_order = appsync.CfnResolver(self, "post-order",
        api_id=api.attr_api_id,
        field_name="postOrder",
        type_name="mutation")

        update_order = appsync.CfnResolver(self, "update-order",
        api_id=api.attr_api_id,
        field_name="updateOrder",
        type_name="mutation")

        delete_order = appsync.CfnResolver(self, "delete-order",
        api_id=api.attr_api_id,
        field_name="deleteOrder",
        type_name="mutation")

