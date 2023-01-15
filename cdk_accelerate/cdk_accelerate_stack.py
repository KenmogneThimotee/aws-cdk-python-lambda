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
import aws_cdk.aws_logs as logs
import aws_cdk.aws_stepfunctions as stepfunctions
from aws_cdk import aws_stepfunctions_tasks as tasks
from string import Template
import json


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

        

        deadLetterQueue = sqs.DeadLetterQueue(max_receive_count=1, queue=queue)
        
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

        cloudWatch_log_role = iam.Role(self, "CloudWatchLogRole",
            assumed_by=iam.ServicePrincipal("appsync.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_managed_policy_arn(self,"cloudWatchLogRole",'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess')])

        log_config= appsync.CfnGraphQLApi.LogConfigProperty(
        cloud_watch_logs_role_arn=cloudWatch_log_role.role_arn,
        exclude_verbose_content=False,
        field_log_level="ALL")


        api = appsync.CfnGraphQLApi(self, "Api", 
        name="demo",
        authentication_type="API_KEY",
        xray_enabled=True,
        log_config=log_config
        )

        api.add_dependency(queue)

        # Setting GraphQl schema
        data_schema = ''
        with open(os.path.join(dirname, "../schema.graphql"), 'r') as file:
            data_schema = file.read().replace('\n', '')

        schema = appsync.CfnGraphQLSchema(scope=self, id="schema", api_id=api.attr_api_id, definition=data_schema)

        # Lambda functions

        lambda_step_function_role = iam.Role(self, "LambdaStepFunctionRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name('AmazonDynamoDBFullAccess'),
        iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSNSFullAccess')])


        cancel_failed_order = ''
        with open("lambdas/cancel_failed_order.py", 'r') as file:
            cancel_failed_order = file.read()

        cancel_failed_order_function = lambda_.CfnFunction(self, "cancel-failed-order-function",
            code=lambda_.CfnFunction.CodeProperty(
                zip_file=cancel_failed_order
            ),
            role=lambda_step_function_role.role_arn,

            # the properties below are optional
            architectures=["x86_64"],
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "ORDER_TABLE": "ORDER",
                    "TOPIC_ARN": cfn_topic.attr_topic_arn
                }
            ),
            function_name="cancel-failed-order-function",
            handler="index.handler",
            package_type="Zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )

        complete_order = ''
        with open("lambdas/complete_order.py", 'r') as file:
            complete_order = file.read()

        complete_order_function = lambda_.CfnFunction(self, "complete-order-function",
            code=lambda_.CfnFunction.CodeProperty(
                zip_file=complete_order
            ),
            role=lambda_step_function_role.role_arn,

            # the properties below are optional
            architectures=["x86_64"],
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "ORDER_TABLE": "ORDER",
                    "TOPIC_ARN": cfn_topic.attr_topic_arn
                }
            ),
            function_name="complete-order-function",
            handler="index.handler",
            package_type="Zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )


        initialize_order = ''
        with open("lambdas/initialize_order.py", 'r') as file:
            initialize_order = file.read()

        initialize_order_function = lambda_.CfnFunction(self, "initialize-order-function",
            code=lambda_.CfnFunction.CodeProperty(
                zip_file=initialize_order
            ),
            role=lambda_step_function_role.role_arn,

            # the properties below are optional
            architectures=["x86_64"],
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "ORDER_TABLE": "ORDER",
                    "TOPIC_ARN": cfn_topic.attr_topic_arn
                }
            ),
            function_name="initialize-order-function",
            handler="index.handler",
            package_type="Zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )

        process_payment = ''
        with open("lambdas/process_payment.py", 'r') as file:
            process_payment = file.read()

        process_payment_function = lambda_.CfnFunction(self, "process-payment-function",
            code=lambda_.CfnFunction.CodeProperty(
                zip_file=process_payment
            ),
            role=lambda_step_function_role.role_arn,

            # the properties below are optional
            architectures=["x86_64"],
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "ORDER_TABLE": "ORDER",
                    "TOPIC_ARN": cfn_topic.attr_topic_arn
                }
            ),
            function_name="process-payment-function",
            handler="index.handler",
            package_type="Zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )

        initialize_order_task = tasks.LambdaInvoke(self, "Initialize order",
            lambda_function=initialize_order_function,
        )

        complete_order_task = tasks.LambdaInvoke(self, "Complete order",
            lambda_function=complete_order_function,
        )

        cancel_failed_order_task = tasks.LambdaInvoke(self, "Cancel order",
            lambda_function=cancel_failed_order_function,
        )

        process_payment_task = tasks.LambdaInvoke(self, "Process payment",
            lambda_function=process_payment_function,
        )

        choice_task = stepfunctions.Choice(self, "Payment choice").when(stepfunctions.Condition.string_matches("$.paymentResult.status", "ok"), complete_order_task).otherwise(cancel_failed_order_task)
        
        process_order_state = stepfunctions.Chain.start(initialize_order_task)
        process_payment_state = process_order_state.next(process_payment_task)
        process_payment_state.next(choice_task)



        ##Execution role
        lambda_execution_role = iam.Role(self, "LambdaExecutionRole",
            assumed_by=iam.AnyPrincipal(),
            managed_policies=[iam.ManagedPolicy.from_managed_policy_arn(self,"lambdaexecution",'arn:aws:iam::aws:policy/service-role/AWSLambdaRole')])
        
        sqs_sendMessage_role = iam.Role(self, "SQSSendMessageRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        managed_policies=[iam.ManagedPolicy.from_managed_policy_arn(self,"sqsSendMessage",'arn:aws:iam::aws:policy/AmazonSQSFullAccess'),
        iam.ManagedPolicy.from_managed_policy_arn(self,"cloudWatchLogRole-forLambda",'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess')])

        workflow = ''
        with open("step-function-workflow/workflow.json", 'r') as file:
            workflow = file.read()

        workflow = Template(workflow).substitute(InitializeOrderArn=initialize_order_function.attr_arn,
        ProcessPaymentArn=process_payment_function.attr_arn,CompleteOrderArn=complete_order_function.attr_arn,
        CancelFailedOrderArn=cancel_failed_order_function.attr_arn,dollar="$")

        print(workflow)

        simple_state_machine = stepfunctions.CfnStateMachine(self, "SimpleStateMachine",
            definition=json.loads(workflow),
            role_arn=lambda_execution_role.role_arn
        )

        #simple_state_machine.add_dependency(initialize_order_task)
        

        sendSQSMessage_code = ''
        with open("lambdas/sendSQSMessage.py", 'r') as file:
            sendSQSMessage_code = file.read()

        sendSQSMessage_function = lambda_.CfnFunction(self, "send-sqs-event",
            code=lambda_.CfnFunction.CodeProperty(
                zip_file=sendSQSMessage_code
            ),
            role=sqs_sendMessage_role.role_arn,

            # the properties below are optional
            architectures=["x86_64"],   
            description="lambda-ds",
            environment=lambda_.CfnFunction.EnvironmentProperty(
                variables={
                    "QueueUrl": queue.attr_queue_url
                }
            ),
            function_name="send-sqs-function",
            handler="index.handler",
            package_type="Zip",
            runtime="python3.9",
            timeout=123,
            tracing_config=lambda_.CfnFunction.TracingConfigProperty(
                mode="Active"
            )
        )
        

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
            handler="index.handler",
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
            handler="index.handler",
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
        managed_policies=[iam.ManagedPolicy.from_managed_policy_arn(self,"sqsReceiveMessage",'arn:aws:iam::aws:policy/AmazonSQSFullAccess'),
        iam.ManagedPolicy.from_managed_policy_arn(self,"cloudWatchLogRole-forLambda-post",'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess'),
        iam.ManagedPolicy.from_aws_managed_policy_name('AWSStepFunctionsFullAccess')])


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
                    "ORDER_TABLE": "ORDER",
                    "STATE_MACHINE_ARN": simple_state_machine.attr_arn
                }
            ),
            function_name="post-order-function",
            handler="index.handler",
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
            handler="index.handler",
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
            handler="index.handler",
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
        
        lambda_send_sqs_message_config_property = appsync.CfnDataSource.LambdaConfigProperty(
            lambda_function_arn=sendSQSMessage_function.attr_arn
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

        lambdaSendSQSMessqgeDs = appsync.CfnDataSource(scope=self, id="lambda-post-order-ds", api_id=api.attr_api_id, name="lambda_post_order_ds", type="AWS_LAMBDA",
        lambda_config=lambda_send_sqs_message_config_property, service_role_arn=lambda_execution_role.role_arn)
        lambdaSendSQSMessqgeDs.add_dependency(queue)
        

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
        #### creating the resolver
        post_order = appsync.CfnResolver(self, "post-order",
        api_id=api.attr_api_id,
        field_name="postOrder",
        type_name="Mutation",
        data_source_name=lambdaSendSQSMessqgeDs.name)
        post_order.add_dependency(schema)
        post_order.add_dependency(lambdaSendSQSMessqgeDs)

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

