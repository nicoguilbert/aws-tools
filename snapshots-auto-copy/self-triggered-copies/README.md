# Description

Once everything is setup, this application will manage the copy of the snapshots from a region to another on AWS.
The main Lambda function will be triggered everyday by an AWS CloudWatch Event. This function will check if some snapshots need to be copied. 
If so, it will create a CloudWatch Event that will trigger the EBS and RDS snapshots copy functions with a rate you can decide. 

# Setup

Go to the AWS Console > Lambda. Feel free to change the names of the functions.

## TriggerCopyFunctions

Click on "Create Function". Use the following parameters :

Function Name   |  Runtime
--------------------|-------------
TriggerCopyFunctions | Python 3.7

### Role
This function should at least have these permissions :

```
  {
        "Version": "2012-10-17",
        "Statement": [
          {
            "Effect": "Allow",
            "Action": [
              "lambda:InvokeFunction"
            ],
            "Resource": "arn:aws:lambda:us-west-1:728679744102:function:SEStest"
          }
        ]
   },
```
