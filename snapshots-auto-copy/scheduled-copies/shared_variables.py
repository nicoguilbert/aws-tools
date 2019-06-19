import json
import boto3

# default values.

SOURCE_REGION = 'us-west-1'
DEST_REGION = 'us-west-2'
AWS_ACCOUNT = '728679744102'

EMAIL_SENDER = "nicolasguilbert.tours@gmail.com"
EMAIL_RECIPIENT = "nicolasguilbert.tours@gmail.com"
EMAIL_REGION = "us-west-2"

SNS = boto3.resource('sns')
EMAIL_TOPIC = SNS.Topic('arn:aws:sns:us-west-1:728679744102:EmailsToSend')

# How many days do you want to keep the snapshots
DAYS_OF_RETENTION = 14
RETENTION_TIME = DAYS_OF_RETENTION * 86400

CLIENT_SOURCE = boto3.client('ec2',region_name=SOURCE_REGION)
CLIENT_DEST = boto3.client('ec2', region_name=DEST_REGION)
EC2_RESOURCE = boto3.resource('ec2')

CLIENT_DB_SOURCE = boto3.client("rds", region_name=SOURCE_REGION)
CLIENT_DB_DEST = boto3.client("rds", region_name=DEST_REGION)