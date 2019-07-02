# Description

Once everything is setup, this application will manage the copy of the snapshots from a region to another on AWS.
The main Lambda function will be triggered everyday by an AWS CloudWatch Event. This function will check if some snapshots need to be copied. 
If so, it will create a CloudWatch Event that will trigger the EBS and RDS snapshots copy functions with a rate you can decide. &nbsp;

The copy functions will disable the CloudWatch rule when they are done copying snapshots.

# Setup
 
*I strongly recommend you do not change the names of the functions because they are used everywhere to link the functions between them.*

## EbsSnapshotCopyCrossRegion

Go to the AWS Console > Lambda. &nbsp;

Click on "Create Function". Use the following parameters :

Function Name   |  Runtime
--------------------|-------------
EbsSnapshotCopyCrossRegion | Python 3.7

### Role

This function needs a Role with at least these permissions :

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:CopySnapshot",
                "ec2:CreateSnapshot",
                "ec2:CreateTags",
                "ec2:DeleteTags",
                "ec2:DescribeSnapshots",
                "ec2:DescribeVolumes",
                "ec2:DescribeInstances"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "events:RemoveTargets",
                "events:DeleteRule"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "sns:Publish"
            ],
            "Resource": "*""
        }
    ]
}
```

Permissions > Create role with basic Lambda permissions > Create Function. &nbsp;

In the dashboard of the function : Execution Role > View the {...} role > Add Inline policy > JSON > *CopyPaste these permissions*

### Code

Copy/Paste the code (ebs-copy.py). Do not forget to change the global variables.

### Timeout

Set the timeout to 1 minute. The usual duration of the function is less than 30 seconds.

### The other parameters

You change let unchanged the other parameters.

http://asvignesh.in/aws-lambda-delete-old-ebs-snapshots-using-boto3/

## RdsSnapshotCopyCrossRegion

Go to the AWS Console > Lambda. &nbsp;

Click on "Create Function". Use the following parameters :

Function Name   |  Runtime
--------------------|-------------
RdsSnapshotCopyCrossRegion | Python 3.7

### Role

This function needs a Role with at least these permissions :

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "rds:DescribeDbSnapshots",
                "rds:CopyDbSnapshot",
                "rds:DescribeDbClusters",
                "rds:DescribeDbClusterSnapshots",
                "rds:CopyDbClusterSnapshot",
                "rds:AddTagsToResource"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "events:RemoveTargets",
                "events:DeleteRule"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "sns:Publish"
            ],
            "Resource": "*"
        }
    ]
}
```

### Code

Copy/Paste the code (rds-copy.py). Do not forget to change the global variables.

### Timeout

Set the timeout to 1 minute. The usual duration of the function is less than 30 seconds.

### The other parameters

You change let unchanged the other parameters.

## TriggerSnapshotCopyFunctions

Go to the AWS Console > Lambda. &nbsp;

Click on "Create Function". Use the following parameters :

Function Name   |  Runtime
--------------------|-------------
TriggerCopyFunctions | Python 3.7

### Role

This function needs a Role with at least these permissions :

```
  {
        "Version": "2012-10-17",
        "Statement": [
          {
            "Effect": "Allow",
            "Action": [
              "lambda:InvokeFunction",
              "lambda:AddPermission"
            ],
            "Resource": [
              "arn:aws:lambda:*:728679744102:function:RdsSnapshotCopyCrossRegion",
              "arn:aws:lambda:*:728679744102:function:EbsSnapshotCopyCrossRegion"
              ]
          },
          {
            "Effect": "Allow",
            "Action": [
                "events:PutRule",
                "events:PutTargets",
                "events:EnableRule",
                "events:DescribeRule"
            ],
            "Resource": "*"
          },
          {
            "Effect": "Allow",
            "Action": [
              "ec2:DescribeSnapshots",
              "ec2:DeleteSnapshot"
            ],
            "Resource": "*"
          },
          {
            "Effect": "Allow",
            "Action": [
              "rds:DescribeDbSnapshots",
              "rds:DeleteDbSnapshot",
              "rds:ListTagsForResource"
            ],
            "Resource": "*"
          },
          {
            "Effect": "Allow",
            "Action": [
                "sns:Publish"
            ],
            "Resource": "*"
        }
      ]
  },
```

Don't forget to change the ARN if you have to!


### CloudWatch Event trigger

In the function window > Designer (probably the main window already opened) > Add Trigger > CloudWatch Events. &nbsp;

Scroll down Rule > Create a new rule > *Pick a rule name* > *Pick a rule description* > Schedule Expression

Example : 

Frequency | Expression
----------|------------
10:15 AM (UTC) every day | cron(15 10 \* \* ? \*)

*24 hours clock, so 6:00PM would be cron(0 18....)*

Enable Trigger > Add.

### Code

Copy/Paste the code (trigger.py). Do not forget to change the global variables.

### Save

Once the function is changed the CloudWatch Event will start processing and will trigger this function when you decided to.


# Emails

*These function do not necessarily need to be re-created. They already exist and can work like that, but if you want to have them in the east region then here are the instructions. If you do that and change the names, do not forget to change the arn in the SNS Publish permissions in the previous functions. You might also want to only re-create the Lambda function and subscribe it to the existing topic*

This application uses AWS SES and SNS to send e-mails. For that you need to use an email address verified by AWS. &nbsp;

When a Lambda copy function will have to send an email, it will pusblish a message on the EmailsToSend SNS Topic. This publication will trigger the Lambda function SNSEmailSending that will send the e-mail.

## SNS Topic : "EmailsToSend"

Go to the AWS Console > SNS > Create Topic > Topic Name : "EmailsToSend". You can let all the default parameters unchanged. 

## Lambda function : "SNSEmailSending"

Go to the AWS Console > Lambda. &nbsp;

Click on "Create Function". Use the following parameters :

Function Name   |  Runtime
--------------------|-------------
SNSEmailSending | Python 3.7

### Role

This function needs a Role with at least these permissions :

```
  {
        "Version": "2012-10-17",
        "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
              "ses:SendEmail",
              "ses:SendTemplatedEmail",
              "ses:SendRawEmail"
            ],
            "Resource": "*"
        }
    ]
  }
```

*This role already exists and can be used since it is not region-specific.*

### Timeout

Set the timeout to 1 minute. The usual duration of the function is less than 30 seconds.

### The other parameters

You change let unchanged the other parameters.

### Code

Copy/Paste the code (email-sending.py). Do not forget to change the global variables.

### Trigger

In the function window > Designer (probably the main window already opened) > Add Trigger > SNS. &nbsp;

Select the Topic arn > Enable Trigger > Add. &nbsp;

You should be able to see on SNS if the function has been added to the subscribers.






