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
from aws_cdk.aws_lambda_event_sources import SqsEventSource
from aws_cdk import aws_iam as iam
from aws_cdk import aws_sns as sns
from aws_cdk import aws_dynamodb as dynamodb




dirname = path.dirname(__file__)
class CdkAccelerateStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB

        cfn_table = dynamodb.CfnTable(self, "Table",
            key_schema=[dynamodb.CfnTable.KeySchemaProperty(
                attribute_name="user_id",
                key_type="HASH"
            ),
            dynamodb.CfnTable.KeySchemaProperty(
                attribute_name="id",
                key_type="RANGE"
            )],
            billing_mode="PAY_PER_REQUEST",
            table_name="ORDER",
            attribute_definitions=[dynamodb.CfnTable.AttributeDefinitionProperty(
                attribute_name="user_id",
                attribute_type="S"
            ),
            dynamodb.CfnTable.AttributeDefinitionProperty(
                attribute_name="id",
                attribute_type="S"
            )]
        )

        db_role = iam.Role(self, "DBReadWriteRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name('AmazonDynamoDBFullAccess')])

        # SQS
        queue = sqs.CfnQueue(
            self, "CdkAccelerateQueue",
            visibility_timeout=300,
            queue_name="sqs-queue"
        )

        deadLetterQueue = sqs.DeadLetterQueue(max_receive_count=100, queue=queue)
        
        sqs_role = iam.Role(self, "GrantSendMessage",
            assumed_by=iam.AnyPrincipal(),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSQSFullAccess')])

        # SNS
        cfn_topic = sns.CfnTopic(self, "MyCfnTopic",
            display_name="sns-topic",
            fifo_topic=False,
            subscription=[],
            topic_name="sns-topic"
        )

        sns_policy_document = iam.PolicyDocument(
            statements=[iam.PolicyStatement(
                actions=["sns:Publish","sns:Subscribe"
                ],
                principals=[iam.AnyPrincipal()],
                resources=["*"]
            )]
        )

        cfn_topic_policy = sns.CfnTopicPolicy(self, "MyCfnTopicPolicy",
            policy_document=sns_policy_document,
            topics=[cfn_topic.attr_topic_arn]
        )

        # APPSYNC
        api = appsync.CfnGraphQLApi(self, "Api", 
        name="demo",
        authentication_type="API_KEY"
        )

        api.add_dependency(queue)

        # Setting GraphQl schema
        data_schema = ''
        with open(os.path.join(dirname, "../schema.graphql"), 'r') as file:
            data_schema = file.read().replace('\n', '')

        schema = appsync.CfnGraphQLSchema(scope=self, id="schema", api_id=api.attr_api_id, definition=data_schema)

        # Lambda functions

        ##Execution role
        lambda_execution_role = iam.Role(self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("appsync.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_managed_policy_arn(self,"lambdaexecution",'arn:aws:iam::aws:policy/service-role/AWSLambdaRole')])

        ## Delete order function
        delete_function = ''
        with open("lambdas/delete_order.py", 'r') as file:
            delete_function = file.read()

        deleteDs_function = lambda_.CfnFunction(self, "delete",
            code=lambda_.CfnFunction.CodeProperty(
                zip_file=delete_function
            ),
            role=db_role.role_arn,

            # the properties below are optional
            architectures=["x86_64"],
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "ORDER_TABLE": "ORDER"
                }
            ),
            function_name="delete-order-function",
            handler="handler",
            package_type="Zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )

        ## Update order function
        update_function = ''
        with open("lambdas/update_order.py", 'r') as file:
            update_function = file.read()

        updateDs_function = lambda_.CfnFunction(self, "update",
            code=lambda_.CfnFunction.CodeProperty(
                zip_file=update_function
            ),
            role=db_role.role_arn,

            # the properties below are optional
            architectures=["x86_64"],
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "ORDER_TABLE": "ORDER"
                }
            ),
            function_name="update-order-function",
            handler="handler",
            package_type="Zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )


        ## Post order function
        sqs_receiveMessage_role = iam.Role(self, "SQSReceiveMessageRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        managed_policies=[iam.ManagedPolicy.from_managed_policy_arn(self,"sqsReceiveMessage",'arn:aws:iam::aws:policy/AmazonSQSFullAccess')])


        post_function = ''
        with open("lambdas/post_order.py", 'r') as file:
            post_function = file.read()

        post_function = lambda_.CfnFunction(self, "post",
            code=lambda_.CfnFunction.CodeProperty(
                zip_file=post_function
            ),
            role=sqs_receiveMessage_role.role_arn,

            # the properties below are optional
            architectures=["x86_64"],
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "ORDER_TABLE": "ORDER"
                }
            ),
            function_name="post-order-function",
            handler="handler",
            package_type="Zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )
        event_source_mapping = lambda_.EventSourceMapping(scope=self, id="MyEventSourceMapping",
            target=post_function,
            batch_size=5,
            enabled=True,
            event_source_arn=queue.attr_arn)
        

        


        ## Get order by id function
        getById_function = ''
        with open("lambdas/get_single_order.py", 'r') as file:
            getById_function = file.read()

        getByIdDs_function = lambda_.CfnFunction(self, "get",
            code=lambda_.CfnFunction.CodeProperty(
                zip_file=getById_function
            ),
            role=db_role.role_arn,

            # the properties below are optional
            architectures=["x86_64"],
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "ORDER_TABLE": "ORDER"
                }
            ),
            function_name="get-order-function",
            handler="handler",
            package_type="Zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )

        ## Get all order function
        getAll_function = ''
        with open("lambdas/get_orders.py", 'r') as file:
            getAll_function = file.read()

        getAllDs_function = lambda_.CfnFunction(self, "gets",
            code=lambda_.CfnFunction.CodeProperty(
                zip_file=getAll_function
            ),
            role=db_role.role_arn,

            # the properties below are optional
            architectures=["x86_64"],
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "ORDER_TABLE": "ORDER"
                }
            ),
            function_name="get-orders-function",
            handler="handler",
            package_type="Zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )
        
        #Data source config property
        lambda_delete_order_config_property = appsync.CfnDataSource.LambdaConfigProperty(
            lambda_function_arn=deleteDs_function.attr_arn
        )

        lambda_update_order_config_property = appsync.CfnDataSource.LambdaConfigProperty(
            lambda_function_arn=updateDs_function.attr_arn
        )

        lambda_getById_order_config_property = appsync.CfnDataSource.LambdaConfigProperty(
            lambda_function_arn=getByIdDs_function.attr_arn
        )

        lambda_getAll_order_config_property = appsync.CfnDataSource.LambdaConfigProperty(
            lambda_function_arn=getAllDs_function.attr_arn
        )
        
        region = Stack.of(self).region
        print("region", region)
        http_config_property = appsync.CfnDataSource.HttpConfigProperty(
            endpoint=queue.attr_queue_url,

            authorization_config=appsync.CfnDataSource.AuthorizationConfigProperty(
                authorization_type="AWS_IAM",

                aws_iam_config=appsync.CfnDataSource.AwsIamConfigProperty(
                    signing_region="us-east-1",
                    signing_service_name="sqs"
                )
            )
        )


        #Data source definition
        lambdaDeleteOrderDs = appsync.CfnDataSource(scope=self, id="lambda-delete-order-ds", api_id=api.attr_api_id, name="lambda_delete_order_ds", type="AWS_LAMBDA",
        lambda_config=lambda_delete_order_config_property, service_role_arn=lambda_execution_role.role_arn)

        lambdaUpdateOrderDs = appsync.CfnDataSource(scope=self, id="lambda-update-order-ds", api_id=api.attr_api_id, name="lambda_update_order_ds", type="AWS_LAMBDA",
        lambda_config=lambda_update_order_config_property, service_role_arn=lambda_execution_role.role_arn)

        lambdaGetOrderByIdDs = appsync.CfnDataSource(scope=self, id="lambda-get-order-ds", api_id=api.attr_api_id, name="lambda_get_order_ds", type="AWS_LAMBDA",
        lambda_config=lambda_getById_order_config_property, service_role_arn=lambda_execution_role.role_arn)

        lambdaGetAllOrderDs = appsync.CfnDataSource(scope=self, id="lambda-getAll-order-ds", api_id=api.attr_api_id, name="lambda_getAll_order_ds", type="AWS_LAMBDA",
        lambda_config=lambda_getAll_order_config_property, service_role_arn=lambda_execution_role.role_arn)

        lambdaPostOrderDs = appsync.CfnDataSource(scope=self, id="lambda-post-order-ds", api_id=api.attr_api_id, name="lambda_post_order_ds", type="HTTP",
        http_config=http_config_property,service_role_arn=lambda_execution_role.role_arn)
        lambdaPostOrderDs.add_dependency(post_function)
        lambdaPostOrderDs.add_dependency(queue)
        

        #Resolvers
        ## list orders resolver
        list_orders = appsync.CfnResolver(self, "list-orders",
        api_id=api.attr_api_id,
        field_name="orders",
        type_name="Query",
        data_source_name=lambdaGetAllOrderDs.name)
        list_orders.add_dependency(schema)
        list_orders.add_dependency(lambdaGetAllOrderDs)
        
        ## get order resolver
        get_order = appsync.CfnResolver(self, "get-order",
        api_id=api.attr_api_id,
        field_name="order",
        type_name="Query",
        data_source_name=lambdaGetOrderByIdDs.name)
        get_order.add_dependency(schema)
        get_order.add_dependency(lambdaGetOrderByIdDs)

        ##  post order resolvers
        ### reading the request mapping template
        request_mapping_template = ''
        with open("requestMappingTemplate.vtl", 'r') as file:
            request_mapping_template = file.read().replace('\n', '')
        
        account_id = Stack.of(self).account
        request_mapping_template.format(accountId=account_id, queueName=queue.queue_name)

        ### reading the response mapping template
        response_mapping_template = ''
        with open("responseMappingTemplate.vtl", 'r') as file:
            response_mapping_template = file.read().replace('\n', '')
        #### creating the resolver
        post_order = appsync.CfnResolver(self, "post-order",
        api_id=api.attr_api_id,
        field_name="postOrder",
        type_name="Mutation",
        data_source_name=lambdaPostOrderDs.name,
        request_mapping_template=request_mapping_template,
        response_mapping_template=response_mapping_template)
        post_order.add_dependency(schema)
        post_order.add_dependency(lambdaPostOrderDs)

        ## update order resolver
        update_order = appsync.CfnResolver(self, "update-order",
        api_id=api.attr_api_id,
        field_name="updateOrder",
        type_name="Mutation",
        data_source_name=lambdaUpdateOrderDs.name)
        update_order.add_dependency(schema)
        update_order.add_dependency(lambdaUpdateOrderDs)

        ## delete order resolver
        delete_order = appsync.CfnResolver(self, "delete-order",
        api_id=api.attr_api_id,
        field_name="deleteOrder",
        type_name="Mutation",
        data_source_name=lambdaDeleteOrderDs.name)
        delete_order.add_dependency(schema)
        delete_order.add_dependency(lambdaDeleteOrderDs)

