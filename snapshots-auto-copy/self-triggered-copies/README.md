# Description

Once everything is setup, this application will manage the copy of the snapshots from a region to another on AWS.
The main Lambda function will be triggered everyday by an AWS CloudWatch Event. This function will check if some snapshots need to be copied. 
If so, it will create a CloudWatch Event that will trigger the EBS and RDS snapshots copy functions with a rate you can decide. 

# Setup
 
*Feel free to change the names of the functions but make sure to change the ARN too if you do. You should also be careful with the resources the permissions are targeted to.*

## EbsSnapshotCopyCrossRegion

Go to the AWS Console > Lambda.
Click on "Create Function". Use the following parameters :

Function Name   |  Runtime
--------------------|-------------
EbsSnapshotCopyCrossRegion | Python 2.7

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
                "ec2:DeleteSnapshot"
            ],
            "Resource": "arn:aws:ec2:us-west-2:728679744102:*"
        }
    ]
}
```


http://asvignesh.in/aws-lambda-delete-old-ebs-snapshots-using-boto3/

## TriggerCopyFunctions

Go to the AWS Console > Lambda.
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
              "arn:aws:lambda:us-west-1:728679744102:function:RdsSnapshotCopyCrossRegion",
              "arn:aws:lambda:us-west-1:728679744102:function:EbsSnapshotCopyCrossRegion"
              ]
          }
      ]
  },
```


