################################################################
# This script copies every snapshot from us-west-2 to us-west-1
# Python 3.7
################################################################

import boto3
import botocore
import time
import datetime
import operator
import re
import json

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

EMAIL_SENDER = "nicolasguilbert.tours@gmail.com"
EMAIL_RECIPIENT = "nicolasguilbert.tours@gmail.com"
EMAIL_REGION = "us-west-2"
TOPIC_ARN = "arn:aws:sns:us-west-1:728679744102:EmailsToSend"

# How many days do you want to keep the snapshots
DAYS_OF_RETENTION = 15
RETENTION_TIME = DAYS_OF_RETENTION * 86400

######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
######################################################################################
# Original function (lot of typos like double quotes missing)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################

# Global function
def delete_rule(context):
        events_client = boto3.client('events') 
        events_client.remove_targets( 
            Rule="{0}-Trigger".format(context.function_name), 
            Ids=[ 
                '2', 
            ] 
        ) 
        events_client.delete_rule( 
            Name="{0}-Trigger".format(context.function_name) 
        )

class RdsWorkUnit(object):
    ''' This class represents a work unit for processing the copy of the snapshots on various regions.
    '''

    def __init__(self, region_source, region_dest, snap_type):
        self.region_source = region_source
        self.region_dest = region_dest
        self.snap_type = snap_type

        self.aws_account = ACCOUNT
        self.email_sender = EMAIL_SENDER
        self.email_recipient = EMAIL_RECIPIENT
        self.email_region = EMAIL_REGION

        self.client_db_source = boto3.client("rds", region_name=self.region_source)
        self.client_db_dest = boto3.client("rds", region_name=self.region_dest)
        self.sns = boto3.resource('sns')
        self.email_topic = self.sns.Topic(TOPIC_ARN)

        self.snapshots_list = []

    def send_email(self, subject, message):
        print ("Sending email.")
        self.email_topic.publish(
                Subject = subject,
                Message = message
            )
        print ("Email sent.")

    def handle_error(self, email_subject, resource_type, resource_info, action, region, error):
        self.send_email(
            subject = email_subject,
            message = """
                {
                    "sender": "Sender Name  <%s>",
                    "recipient":"%s",
                    "aws_region":"%s",
                    "body": "Resource Type : %s || Resource : %s || Region : %s || Action : %s || Error : %s"
                }
            """ % (self.email_sender, self.email_recipient, self.email_region, resource_type, resource_info, region, action, error)
        )
        print("Resource Type : %s .\n Resource Id : %s .\n Region : %s .\n Process : %s .\n Error : %s" % (resource_type, resource_info, region, action, error))

    def add_tag_to_snapshot(self, key, value, copy_name):
        response = self.client_db_dest.add_tags_to_resource(
            ResourceName=copy_name,
            Tags=[
                {
                    'Key': key,
                    'Value': value
                },
            ]
        )

    def sort_snapshots_by_time(self):
        self.snapshots_list.sort(key=lambda r:r[2], reverse=True)
        print("### List sorted.")

    def get_snapshots_to_copy(self):
        # DOES NOT WORK FOR AURORA ! ! !
        response = self.client_db_source.describe_db_snapshots(
            SnapshotType=self.snap_type,
            IncludeShared=False,
            IncludePublic=False
        )
        return response['DBSnapshots']

    def get_copy_name(self, database, snapshot_name, start_time):
        if self.snap_type == "automated":
            copy_name = "sc-" + database + "-" + start_time.strftime("%Y-%m-%d-%Hh%Mm")
        elif self.snap_type == "manual":
            copy_name = "sc-" + snapshot_name + "-" + start_time.strftime("%Y-%m-%d-%Hh%Mm")

        return copy_name

    def is_copied(self, copy_name):
        print("Checking if " + copy_name + " is copied")

        try:
            self.client_db_dest.describe_db_snapshots(
                DBSnapshotIdentifier=copy_name
            )
            print("Already Copied")

            return True
        except:
            return False
    
    def init_snapshots_list(self):
        nb_snapshots_to_copy = 0
        snapshots = self.get_snapshots_to_copy()

        for snapshot in snapshots:
            if snapshot['Status'] != 'available':
                continue
        
            database = snapshot["DBInstanceIdentifier"]
            start_time = snapshot["SnapshotCreateTime"]
            snapshot_name = snapshot["DBSnapshotIdentifier"]

            ###################################################################
            # Naming rule for the new snapshot :
            # Automated => Name of database + Creation date (year-month-day)
            # Manual    => Name of the snapshot + Creation date 
            ###################################################################
        
            copy_name = self.get_copy_name(database, snapshot_name, start_time)
            
            if self.is_copied(copy_name) == False:
                self.snapshots_list.append((database, snapshot_name, start_time))
                nb_snapshots_to_copy = nb_snapshots_to_copy + 1

        self.sort_snapshots_by_time()

        print(str(nb_snapshots_to_copy) + " RDS " + self.snap_type + " snapshots to copy in " + self.region_source)
        return nb_snapshots_to_copy

    def copy_snapshot(self, snapshot, copy_name):
        try:
            response = self.client_db_dest.copy_db_snapshot(
                SourceDBSnapshotIdentifier='arn:aws:rds:' + self.region_source + ':' + self.aws_account + ':snapshot:' + snapshot[1],
                TargetDBSnapshotIdentifier=copy_name,
                CopyTags=True
            )
            return response

        except botocore.exceptions.ClientError as err:
            print("Snapshots copy limit reached on that region.")
            return "CopyLimitException"

        except Exception as err:
            self.handle_error(
                    email_subject="RDS Snapshot copy failed",
                    resource_type="RDS Snapshot", 
                    resource_info=copy_name, 
                    region=self.region_source, 
                    action= "Copy cross region", 
                    error=str(err)
                )
            print(err)
            return "Error"

    def copy_snapshots(self):    
        nb_snapshots_copied = 0
    
        for s in self.snapshots_list:
            # s[0] : db name, s[1] : snapshot name, s[2] : start_time
            copy_name = self.get_copy_name(s[0], s[1], s[2])
            copy_response = self.copy_snapshot(s, copy_name)

            if copy_response == "CopyLimitException":
                return copy_response

            if copy_response == "Error":
                continue
            
            nb_snapshots_copied = nb_snapshots_copied + 1
            self.add_tag_to_snapshot("OriginalSnapshotID", s[1], copy_response["DBSnapshot"]["DBSnapshotArn"])
            print("Snapshot " + copy_name + " successfully copied on region " + self.region_dest)

        print("No more snapshots to copy on " + str(self.region_source))
        return True

def lambda_handler(event, context):
    delete_rule_flag = True

    for copy_order in COPY_DEFINITIONS:
        ####################
        # manual snapshots #
        ####################
        manual_work_unit = RdsWorkUnit(copy_order["Source"], copy_order["Destination"], "manual")
        manual_work_unit.init_snapshots_list()
        copy_response = manual_work_unit.copy_snapshots()

        if copy_response == "CopyLimitException":
            delete_rule_flag = False

        #######################
        # automated snapshots #
        #######################
        automated_work_unit = RdsWorkUnit(copy_order["Source"], copy_order["Destination"], "automated")
        automated_work_unit.init_snapshots_list()
        copy_response = automated_work_unit.copy_snapshots()

        if copy_response == "CopyLimitException":
            delete_rule_flag = False
    
    # If there's nothing to copy, it deletes the cloudwatch rule
    if delete_rule_flag == True:
        print("delete_rule")
        delete_rule(context)

