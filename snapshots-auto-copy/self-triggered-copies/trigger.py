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
        "Source" : "us-east-2",
        "Destination" : "us-east-1"
    }#,
    #{
    #   "Source" : "us-east-2",
    #   "Destination" : "us-east-1"
    #}, ....
]

ACCOUNT = "728679744102"

# How many days do you want to keep the snapshots
DAYS_OF_RETENTION = 14

EMAIL_SENDER = "SysAdmin-AWS@doxcelerate.com"
EMAIL_RECIPIENT = "SysAdmin-AWS@doxcelerate.com"
EMAIL_REGION = "us-east-1"
TOPIC_ARN = "arn:aws:sns:us-east-2:728679744102:EmailsToSend"

SNS = boto3.resource('sns')
EMAIL_TOPIC = SNS.Topic(TOPIC_ARN)

ebs_fn_name = "EbsSnapshotCopyCrossRegion"
ebs_fn_arn = 'arn:aws:lambda:us-east-2:728679744102:function:EbsSnapshotCopyCrossRegion'
    
rds_fn_name = "RdsSnapshotCopyCrossRegion"
rds_fn_arn = 'arn:aws:lambda:us-east-2:728679744102:function:RdsSnapshotCopyCrossRegion'


# The functions will be called at this frequency!
frequency = "rate(5 minutes)"

ebs_trigger_name = "{0}-Trigger".format(ebs_fn_name)
rds_trigger_name = "{0}-Trigger".format(rds_fn_name)

def my_send_email(subject, message): 
    print ("DOX-INFO : Sending email.") 
    try: 
        EMAIL_TOPIC.publish( 
            Subject = subject, 
            Message = message 
        ) 
        print ("DOX-INFO : Email sent.") 
    except Exception as err: 
        print (err) 
    
def handle_error(email_subject, resource_type, resource_info, action, region, error):
    my_send_email(
        subject = email_subject,
        #https://stackoverflow.com/questions/22394235/invalid-control-character-with-python-json-loads
        # 'r' before a string makes control character possible.
        message = r"""
            {
                "sender": "%s",
                "recipient":"%s",
                "aws_region":"%s",
                "body": "Resource Type : %s \nResource : %s \nRegion : %s \nAction : %s \nError : %s"
            }
            """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION, resource_type, resource_info, region, action, error)
        )
    print("Resource Type : %s . Resource Id : %s . Region : %s . Process : %s . Error : %s" % (resource_type, resource_info, region, action, error))

class Ec2WorkUnit(object):
    ''' Work unit for processing deletion of the EBS snapshots
    '''

    def __init__(self, region_source, region_dest):
        self.region_source = region_source
        self.region_dest = region_dest

        self.ec2_source = boto3.client('ec2', region_name=region_source)
        self.ec2_dest = boto3.client('ec2', region_name=region_dest)
    
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
                    ACCOUNT, 
                ],
            )
            #print(original_snapshot_id + " snapshot still exists. Not deleting its copy.")
            return True
        except Exception as err:
            #print(err)
            #print("Original Snapshot ID : " + original_snapshot_id + " doesn't exist.")
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
                ACCOUNT, 
            ],
        )
        # snapshots = {"Snapshots": [ {} ],  } ===> link to boto3
        return snapshots

    def get_delete_time(self, older_days):
        delete_time = datetime.now(tz=timezone.utc) - timedelta(days=older_days)
        return delete_time

    def delete_snapshots(self, older_days=15):
        delete_snapshots_num = 0

        snapshots = self.get_autocopied_snapshots()
        
        for snapshot in snapshots['Snapshots']:
            try:
                original_snapshot_id = self.get_original_snapshot_id(snapshot)
            except Exception as err:
                print("Couldn't get original snapshot id for snapshot " + snapshot['SnapshotId'] + " : " + str(err))
                continue
            if self.original_exists(original_snapshot_id):
                continue
            
            start_time = snapshot['StartTime']
            if (start_time < self.get_delete_time(older_days)):
                try:
                    self.delete_snapshot(snapshot['SnapshotId'])
                except:
                    #print ("This snapshot was probably 'InUse' by an Image. Won't be deleted.")
                    continue
                else:
                    delete_snapshots_num = delete_snapshots_num + 1
                    print("DOX-INFO : EBS Copy Snapshot in destination region : " + snapshot['SnapshotId'] + " got deleted.")
                    
        print("DOX-RESULT : " + str(delete_snapshots_num) + " EBS snapshots deleted on region " + self.region_dest)
        return delete_snapshots_num

class RdsWorkUnit(object):

    def __init__(self, region_source, region_dest):
        self.region_source = region_source
        self.region_dest = region_dest

        self.client_db_source = boto3.client("rds", region_name=self.region_source)
        self.client_db_dest = boto3.client("rds", region_name=self.region_dest)

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
            #print(original_snapshot_id + " snapshot still exists. Not deleting its copy.")
            return True
        except:
            #print(original_snapshot_id + " snapshot doesn't exist. Deleting its copy.")
            return False
              
    def delete_snapshot(self, snapshot_id):
        self.client_db_dest.delete_db_snapshot(
                    DBSnapshotIdentifier = snapshot_id
                )
        #print(snapshot_id + " deleted.")

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
            elif self.original_exists(original_snapshot_id):
                continue
                
            start_time = snapshot['SnapshotCreateTime'].replace(tzinfo=None)
            if start_time < delete_time:
                self.delete_snapshot(snapshot['DBSnapshotIdentifier'])
                print("DOX-INFO : RDS Copy Snapshot on destination region " + snapshot['DBSnapshotIdentifier'] + " got deleted.")
                n = n + 1

        print("DOX-RESULT : " + str(n) + " RDS snapshots deleted on region " + self.region_dest)
        return n


# Main function (called by Lambda)
def lambda_handler(event, context):
    lambda_client = boto3.client('lambda')
    events_client = boto3.client('events')

    ########
    # EBS. #
    ########

    try:
        '''
            * This instruction checks if the rule already exists.
                If it does exist, it means the function has been processing for 24 hours.
                If so, the code is sending an email to notice Doxcelerate.
            * The expected behavior is that this instruction will fail because the rule has been deleted.
                An exception will be raised and it will jump to the except block, which is what we want.
        '''
        response_test = events_client.describe_rule(
            Name=ebs_trigger_name
        )    

    except:
        '''
            * Executed to create the CW rule.
        '''

        # Creates the rule with wanted parameters.
        rule_response = events_client.put_rule(
            Name=ebs_trigger_name,
            ScheduleExpression=frequency,
            State='ENABLED',
        )   

        # Gives the rule the permission to invoke the EBS function.
        lambda_client.add_permission(
            FunctionName=ebs_fn_name,
            StatementId="{0}-Event".format(ebs_fn_name),
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rule_response['RuleArn'],
        )
        
        # Links the event to the function.
        events_client.put_targets(
            Rule=ebs_trigger_name,
            Targets=[
                {
                    'Id': "1",
                    'Arn': ebs_fn_arn,
                },
            ]
        )

        #print("DOX - SUCCESS : Ebs rule created.")
    else:
        '''
            * Block executed if the 'try' succeeds (which it should not)
        '''
        handle_error(
            email_subject="EBS Snapshot CloudWatch still running!",
            resource_type="EBS copy function", 
            resource_info="Error happened in trigger function", 
            region="N/A", 
            action= "Trigger", 
            error="The EBS copy function is still running 24 hours later !"
        )
        print("DOX - ERROR : EBS rule still exists")
        #print(response_test)


    ########
    # RDS. #
    ########

    '''
        Works the same as EBS.
    '''
    try:
        response_test_rds = events_client.describe_rule(
            Name=rds_trigger_name
        )
    
    except:
        rds_rule_response = events_client.put_rule(
            Name=rds_trigger_name,
            ScheduleExpression=frequency,
            State='ENABLED',
        )  

        lambda_client.add_permission(
            FunctionName=rds_fn_name,
            StatementId="{0}-Event".format(rds_fn_name),
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rds_rule_response['RuleArn'],
        )

        events_client.put_targets(
            Rule=rds_trigger_name,
            Targets=[
                {
                    'Id': "2",
                    'Arn': rds_fn_arn,
                },
            ]
        )
        #print("DOX - SUCCESS : RDS RULE CONFIGURED.") 

    else:
        '''
            * Executed if the 'try' block succeeds (which it should not)
        '''
        handle_error(
            email_subject="RDS Snapshot CloudWatch still running!",
            resource_type="RDS copy function", 
            resource_info="Error happened in trigger function", 
            region="N/A", 
            action= "Trigger", 
            error="The RDS copy function is still running 24 hours later !"
        )
        print("DOX - ERROR : RDS rule still exists")
        #print(response_test_rds)

    
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
