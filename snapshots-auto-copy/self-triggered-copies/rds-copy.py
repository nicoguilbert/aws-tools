################################################################
# This script copies every snapshot from us-west-2 to us-west-1
# Python 3.7
################################################################

import boto3
import time
import datetime
import operator
import re
import json

######################
#  Global variables. #
######################

REGIONS = [
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

# Object independant function
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

class RdsDB(object):

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
        self.snapshots = []

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

    def add_tag(self, key, value, copy_name):
        response = self.client_db_dest.add_tags_to_resource(
            ResourceName=copy_name,
            Tags=[
                {
                    'Key': key,
                    'Value': value
                },
            ]
        )

    def sort(self):
        self.snapshots.sort(key=lambda r:r[2], reverse=True)
        print("### List sorted.")

    def get_nb_copy(self):
        response = self.client_db_dest.describe_db_snapshots(
            IncludeShared=False,
            IncludePublic=False
        )
        snapshots = response['DBSnapshots']
        nb_copy = 0
    
        for snapshot in snapshots:
            if snapshot["Status"] == 'pending' or snapshot["Status"] == 'creating':
                nb_copy = nb_copy + 1
        print(str(nb_copy) + " snapshots copying on " + self.region_dest)
        return nb_copy

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

    def already_copied(self, copy_name):
        print("Checking if " + copy_name + " is copied")

        try:
            self.client_db_dest.describe_db_snapshots(
                DBSnapshotIdentifier=copy_name
            )
            print("Already Copied")

            return True
        except:
            return False
    
    def set_snapshots(self):
        n = 0
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
            if self.already_copied(copy_name) == False:
                self.snapshots.append((database, snapshot_name, start_time))
                n = n + 1

        self.sort()
        print(str(n) + " RDS " + self.snap_type + " snapshots to copy in " + self.region_source)
        return n

    def copy_snapshot(self, snapshot, copy_name):
        response = self.client_db_dest.copy_db_snapshot(
            SourceDBSnapshotIdentifier='arn:aws:rds:' + self.region_source + ':' + self.aws_account + ':snapshot:' + snapshot[1],
            TargetDBSnapshotIdentifier=copy_name,
            CopyTags=True
        )
        return response

    def copy_snapshots(self, copy_limit):    
        n = 0
    
        for s in self.snapshots:
            copy_name = self.get_copy_name(s[0], s[1], s[2])
            response = self.copy_snapshot(s, copy_name)

            if response['DBSnapshot']['Status'] != "pending" and response['DBSnapshot']['Status'] != "available":
                print("Error : Copy operation for " + copy_name + " failed!") 
                print(response)              
                
                self.handle_error(
                    email_subject="RDS Snapshot copy failed",
                    resource_type="RDS Snapshot", 
                    resource_info=copy_name, 
                    region=self.region_source, 
                    action= "Copy cross region", 
                    error=str(response)
                )
                continue
            
            n = n + 1
            self.add_tag("OriginalSnapshotID", s[1], response["DBSnapshot"]["DBSnapshotArn"])
            print("Snapshot " + copy_name + " successfully copied on region " + self.region_dest)
            # if 5 snapshots are already being copied, it returns the number of snapshots left to copy. 
            if n == copy_limit:
                break
        return n

def lambda_handler(event, context):
    nb_copy_processing = 0
    nb_to_copy = 0
    total_to_copy = 0
    i = 0
    rds = []

    for region in REGIONS:
        ####################
        # manual snapshots #
        ####################
        o_rds_manual = RdsDB(region["Source"], region["Destination"], "manual")

        nb_copy_processing = nb_copy_processing + o_rds_manual.get_nb_copy()
        if nb_copy_processing >= 5:
            print("Already 5 snapshots being copied. Waiting for the next call.")
            return 0

        nb_to_copy = o_rds_manual.set_snapshots()
        #print("nb_to_copy" + str(nb_to_copy))
        if nb_to_copy > 0:
            rds.append(o_rds_manual)
            total_to_copy = total_to_copy + nb_to_copy
            i = i + 1

        if total_to_copy >= 5 - nb_copy_processing:
            break

        #######################
        # automated snapshots #
        #######################
        o_rds_auto = RdsDB(region["Source"], region["Destination"], "automated")
        
        nb_to_copy = o_rds_auto.set_snapshots()
        #print("nb_to_copy" + str(nb_to_copy))
        if nb_to_copy > 0:
            rds.append(o_rds_auto)
            total_to_copy = total_to_copy + nb_to_copy
            i = i + 1

        if total_to_copy >= 5 - nb_copy_processing:
            break

    # If there's nothing to copy, it deletes the cloudwatch rule
    if total_to_copy == 0:
        print("delete_rule")
        delete_rule(context)
    
    copy_limit = 5 - nb_copy_processing
    
    nb_copied = 0
    # Launches copy process
    for n in range (0, i):
        if copy_limit <= 0:
            break

        nb_copied = rds[n].copy_snapshots(copy_limit)

        copy_limit = copy_limit - nb_copied
    print(str(nb_copied) + " snapshots copied.")