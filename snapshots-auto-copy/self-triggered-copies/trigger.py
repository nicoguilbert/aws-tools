import boto3
import time
#import datetime
import operator
import re
import json
from datetime import datetime, timedelta, timezone


######################
#  Global variables. #
######################

COPY_DEFINITIONS = [
    {
        "Source" : "us-west-1",
        "Destination" : "us-west-2"
    }#,
    #{
    #   "Source" : "us-east-2",
    #   "Destination" : "us-east-1"
    #}, ....
]

ACCOUNT = "728679744102"

# How many days do you want to keep the snapshots
DAYS_OF_RETENTION = 15

EMAIL_SENDER = "nicolasguilbert.tours@gmail.com"
EMAIL_RECIPIENT = "nicolasguilbert.tours@gmail.com"
EMAIL_REGION = "us-west-2"
TOPIC_ARN = "arn:aws:sns:us-west-1:728679744102:EmailsToSend"
SNS = boto3.resource('sns')
EMAIL_TOPIC = SNS.Topic(TOPIC_ARN)

ebs_fn_name = "EbsSnapshotCopyCrossRegion"
ebs_fn_arn = 'arn:aws:lambda:us-west-1:728679744102:function:EbsSnapshotCopyCrossRegion'
    
rds_fn_name = "RdsSnapshotCopyCrossRegion"
rds_fn_arn = 'arn:aws:lambda:us-west-1:728679744102:function:RdsSnapshotCopyCrossRegion'
    
frequency = "rate(2 minutes)"
ebs_name = "{0}-Trigger".format(ebs_fn_name)
rds_name = "{0}-Trigger".format(rds_fn_name)

def send_email(subject, message):
    print ("Sending email.")
    EMAIL_TOPIC.publish(
        Subject = subject,
        Message = message
    )
    print ("Email sent.")
    
def handle_error(email_subject, resource_type, resource_info, action, region, error):
    send_email(
        subject = email_subject,
        message = """
            {
                "sender": "Sender Name  <%s>",
                "recipient":"%s",
                "aws_region":"%s",
                "body": "Resource Type : %s || Resource : %s || Region : %s || Action : %s || Error : %s"
            }
            """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION, resource_type, resource_info, region, action, error)
        )
    print("Resource Type : %s .\n Resource Id : %s .\n Region : %s .\n Process : %s .\n Error : %s" % (resource_type, resource_info, region, action, error))

class Ec2WorkUnit(object):

    def __init__(self, region_source, region_dest):
        self.region_source = region_source
        self.region_dest = region_dest
        self.aws_account = ACCOUNT
        self.ec2_source = boto3.client('ec2', region_name=region_source)
        self.ec2_dest = boto3.client('ec2', region_name=region_dest)
        self.ec2_resource = boto3.resource('ec2')
        self.sns = boto3.resource('sns')
        self.email_topic = self.sns.Topic(TOPIC_ARN)
    
    def get_original_snapshot_id(self, snapshot):
        for tag in snapshot["Tags"]:
            if tag["Key"] == "OriginalSnapshotID":
                return tag["Value"]
        print("Did not find the OriginalSnapshotID.")
        return "SnapshotIdError"
        
    def original_exists(self, original_snapshot_id):
        try:
            response = self.ec2_source.describe_snapshots(
                Filters=[
                    { 'Name': 'status', 'Values': [ 'completed' ] }
                ],
                SnapshotIds = [
                    original_snapshot_id,    
                ],
                OwnerIds=[ 
                    self.aws_account, 
                ],
            )
            print(original_snapshot_id + " snapshot still exists. Not deleting its copy.")
            return True
        except:
            print(original_snapshot_id + " snapshot doesn't exist. Deleting its copy.")
            return False
    
    def delete_snapshot(self, snapshot_id):
        try:
            self.ec2_dest.delete_snapshot(SnapshotId=snapshot_id)
        except:
            print("Error deleting " + snapshot_id)
            
    def get_autocopied_snapshots(self):
        snapshots = self.ec2_dest.describe_snapshots(
            Filters=[
                { 'Name': 'status', 'Values': [ 'completed' ] },
                { 'Name': 'tag:SnapshotType', 'Values': [ 'AutomatedCopyCrossRegion' ] }
            ],
            OwnerIds=[ 
                self.aws_account, 
            ],
        )
        return snapshots

    def get_delete_time(self, older_days):
        delete_time = datetime.now(tz=timezone.utc) - timedelta(days=older_days)
        return delete_time

    def delete_snapshots(self, older_days=15):
        delete_snapshots_num = 0

        snapshots = self.get_autocopied_snapshots()
        
        for snapshot in snapshots['Snapshots']:
            original_snapshot_id = self.get_original_snapshot_id(snapshot)
            if self.original_exists(original_snapshot_id) == True:
                continue
            start_time = snapshot['StartTime']
            if (start_time < self.get_delete_time(older_days)):
                try:
                    self.delete_snapshot(snapshot['SnapshotId'])
                    delete_snapshots_num = delete_snapshots_num + 1
                    print("Snapshot " + snapshot['SnapshotId'] + " deleted")
                    continue
                except:
                    print ("This snapshot was probably 'InUse' by an Image. Won't be deleted.")
                    continue

        print(str(delete_snapshots_num) + " snapshots deleted on region " + self.region_dest)
        return delete_snapshots_num

class RdsWorkUnit(object):

    def __init__(self, region_source, region_dest):
        self.region_source = region_source
        self.region_dest = region_dest
        self.aws_account = ACCOUNT
        self.client_db_source = boto3.client("rds", region_name=self.region_source)
        self.client_db_dest = boto3.client("rds", region_name=self.region_dest)
        self.sns = boto3.resource('sns')
        self.email_topic = self.sns.Topic(TOPIC_ARN)

    def get_delete_time(self, older_days=15):
        delete_time = datetime.now() - timedelta(days=older_days)
        delete_time = delete_time.replace(tzinfo=None)
        return delete_time
    
    def get_original_snapshot_id(self, snapshot_db_arn):
        response = self.client_db_dest.list_tags_for_resource(
            ResourceName= snapshot_db_arn,
        )
        #print(response)
        tags = response['TagList']
        for tag in tags:
            if tag["Key"] == "OriginalSnapshotID":
                return tag["Value"]
        return "Original snapshot not found"
        
    def original_exists(self, original_snapshot_id):
        try:
            self.client_db_source.describe_db_snapshots(
                DBSnapshotIdentifier = original_snapshot_id
            )
            print(original_snapshot_id + " snapshot still exists. Not deleting its copy.")
            return True
        except:
            print(original_snapshot_id + " snapshot doesn't exist. Deleting its copy.")
            return False
              
    def delete_snapshot(self, snapshot_id):
        self.client_db_dest.delete_db_snapshot(
                    DBSnapshotIdentifier = snapshot_id
                )
        print(snapshot_id + " deleted.")

    def delete_old_snapshots(self, older_days):
        pattern = re.compile("^sc-")
        n = 0
        # DOES NOT WORK FOR AURORA ! ! !
        response = self.client_db_dest.describe_db_snapshots(
            IncludeShared=False,
            IncludePublic=False
        )
        if len(response['DBSnapshots']) == 0:
            print("No snapshot to delete on region " + self.region_dest)
            return 0

        delete_time = self.get_delete_time(older_days)

        for snapshot in response['DBSnapshots']:
            if snapshot['Status'] != 'available':
                continue
            test_match = pattern.match(snapshot['DBSnapshotIdentifier'])
            if test_match == None:
                continue
            
            original_snapshot_id = self.get_original_snapshot_id(snapshot['DBSnapshotArn'])
            if original_snapshot_id == "Original snapshot not found":
                continue
            elif self.original_exists(original_snapshot_id) == True:
                continue
                
            start_time = snapshot['SnapshotCreateTime'].replace(tzinfo=None)
            if start_time < delete_time:
                print("Processing deletion of snapshot " + snapshot['DBSnapshotIdentifier'])
                self.delete_snapshot(snapshot['DBSnapshotIdentifier'])
                n = n + 1

        print(str(n) + " RDS snapshots deleted on region " + self.region_dest)
        return n

def lambda_handler(event, context):
    lambda_client = boto3.client('lambda')
    events_client = boto3.client('events')

    ########
    # EBS. #
    ########
    try:
        response_test = events_client.describe_rule(
            Name=ebs_name
        )
        handle_error(
            email_subject="EBS Snapshot CloudWatch still running!",
            resource_type="EBS copy function", 
            resource_info="Error happened in trigger function", 
            region="N/A", 
            action= "Trigger", 
            error="The EBS copy function is still running 24 hours later !"
        )
        print("EBS rule still exists")
        print(response_test)
    
    except:
        rule_response = events_client.put_rule(
            Name=ebs_name,
            ScheduleExpression=frequency,
            State='ENABLED',
        )   
        print("Creating rule.")

        try:    
            lambda_client.add_permission(
                FunctionName=ebs_fn_name,
                StatementId="{0}-Event".format(ebs_name),
                Action='lambda:InvokeFunction',
                Principal='events.amazonaws.com',
                SourceArn=rule_response['RuleArn'],
            )
            print("Add permission.")

        except:
            print("No add permission.")
        
        rule_response = events_client.enable_rule(
            Name=ebs_name
        )
        events_client.put_targets(
            Rule=ebs_name,
            Targets=[
                {
                    'Id': "1",
                    'Arn': ebs_fn_arn,
                },
            ]
        )
    
    ########
    # RDS. #
    ########
    try:
        response_test_rds = events_client.describe_rule(
            Name=rds_name
        )
        handle_error(
            email_subject="RDS Snapshot CloudWatch still running!",
            resource_type="RDS copy function", 
            resource_info="Error happened in trigger function", 
            region="N/A", 
            action= "Trigger", 
            error="The RDS copy function is still running 24 hours later !"
        )
        print("RDS rule still exists")
        print(response_test_rds)
    
    except:
        rds_rule_response = events_client.put_rule(
            Name=rds_name,
            ScheduleExpression=frequency,
            State='ENABLED',
        )  
        print("Creating rule.")
        try:
            lambda_client.add_permission(
                FunctionName=rds_fn_name,
                StatementId="{0}-Event".format(rds_name),
                Action='lambda:InvokeFunction',
                Principal='events.amazonaws.com',
                SourceArn=rds_rule_response['RuleArn'],
            )
            print("Add permission")
        except:
            print("No Add permission")
    
        rds_rule_response = events_client.enable_rule(
            Name=rds_name
        )
        events_client.put_targets(
            Rule=rds_name,
            Targets=[
                {
                    'Id': "2",
                    'Arn': rds_fn_arn,
                },
            ]
        )
        print("Rule already exists.") 

    ############
    # deletion #
    ############

    for copy_order in COPY_DEFINITIONS:
        #EBS
        ec2_work_unit = Ec2WorkUnit(copy_order["Source"], copy_order["Destination"])
        ec2_work_unit.delete_snapshots(DAYS_OF_RETENTION)
        
        #RDS
        rds_work_unit = RdsWorkUnit(copy_order["Source"], copy_order["Destination"])
        rds_work_unit.delete_old_snapshots(DAYS_OF_RETENTION)
