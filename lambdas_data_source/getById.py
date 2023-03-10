from aws_cdk import aws_lambda as lambda_
import aws_cdk.aws_appsync as appsync



def create_data_source(stack, api, schema, db_role, lambda_execution_role):

    ## Get order by id function
    getById_function = ''
    with open("lambdas/get_single_order.py", 'r') as file:
        getById_function = file.read()

    getByIdDs_function = lambda_.CfnFunction(stack, "get",
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

    lambda_getById_order_config_property = appsync.CfnDataSource.LambdaConfigProperty(
        lambda_function_arn=getByIdDs_function.attr_arn
    )

    lambdaGetOrderByIdDs = appsync.CfnDataSource(scope=stack, id="lambda-get-order-ds", api_id=api.attr_api_id, name="lambda_get_order_ds", type="AWS_LAMBDA",
    lambda_config=lambda_getById_order_config_property, service_role_arn=lambda_execution_role.role_arn)

    ## get order resolver
    get_order = appsync.CfnResolver(stack, "get-order",
    api_id=api.attr_api_id,
    field_name="order",
    type_name="Query",
    data_source_name=lambdaGetOrderByIdDs.name)
    get_order.add_dependency(schema)
    get_order.add_dependency(lambdaGetOrderByIdDs)
