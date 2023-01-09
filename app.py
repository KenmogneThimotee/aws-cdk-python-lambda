#!/usr/bin/env python3

import aws_cdk as cdk

from cdk_accelerate.cdk_accelerate_stack import CdkAccelerateStack


app = cdk.App()
CdkAccelerateStack(app, "cdk-accelerate")

app.synth()
