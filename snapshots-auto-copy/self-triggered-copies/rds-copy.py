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
    }
]

ACCOUNT = "728679744102"

# How many days do you want to keep the snapshots
DAYS_OF_RETENTION = 14

EMAIL_SENDER = "nicolasguilbert.tours@gmail.com"
EMAIL_RECIPIENT = "nicolasguilbert.tours@gmail.com"
EMAIL_REGION = "us-west-2"
TOPIC_ARN = "arn:aws:sns:us-west-1:728679744102:EmailsToSend"

# How many days do you want to keep the snapshots
DAYS_OF_RETENTION = 14
RETENTION_TIME = DAYS_OF_RETENTION * 86400

CLIENT_LAMBDA = boto3.client("lambda", region_name=SOURCE_REGION)

class RdsDB(object):

    def __init__(self, region_source, region_dest, snap_type):
        self.region_source = region_source
        self.region_dest = region_dest
        self.snap_type = snap_type
        self.aws_account = ACCOUNT
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

    def sort(self):
        self.snapshots.sort(key=lambda r:r[2], reverse=True)


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
        return nb_copy

    def get_snapshots(self):
        # DOES NOT WORK FOR AURORA ! ! !
        response = self.client_db_source.describe_db_snapshots(
            SnapshotType=self.snap_type,
            IncludeShared=False,
            IncludePublic=False
        )
        return response['DBSnapshots']

    def get_copy_name(self,database, snapshot_name, start_time):
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
    
    def set_db_snapshots(self):
        n = 0
        snapshots = self.get_snapshots()

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
        
        copy_name = get_copy_name(database, snapshot_name, start_time)
        if self.already_copied(copy_name) == False:
            self.snapshots.append((database, snapshot_name, start_time))
            n = n + 1

        self.sort()
        print(str(n) + " RDS snapshots to copy in " + self.region_source)
        return n

######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
######################################################################################
# Original function (lot of typos like double quotes missing)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################
    
def copy_snapshots(snapshots, snap_type, copy_limit):    
    nb_to_copy = set_db_snapshots()
    
    n = len(snapshot_list)
    i = 0
    
    # info will contain informations about the number of snapshots being copied,
    # and the number of snapshot left to copy
    info = {}
    
    if snapshot_list == []:
        print("No " + snap_type + "snapshots to copy.")
    else:
        for snap in snapshot_list:
            if snap_type == "automated":
                copy_name = "sc-" + snap[0] + "-" + snap[2].strftime("%Y-%m-%d-%Hh%Mm")
            elif snap_type == "manual":
                copy_name = "sc-" + snap[1] + "-" + snap[2].strftime("%Y-%m-%d-%Hh%Mm")
            
            response = CLIENT_DB_DEST.copy_db_snapshot(
                SourceDBSnapshotIdentifier='arn:aws:rds:' + SOURCE_REGION + ':' + AWS_ACCOUNT + ':snapshot:' + snap[1],
                TargetDBSnapshotIdentifier=copy_name,
                CopyTags=True
            )
                
            if response['DBSnapshot']['Status'] != "pending" and response['DBSnapshot']['Status'] != "available":
                raise Exception("Copy operation for " + copy_name + " failed!")               
                
                send_email(
                    subject = "An Rds Snapshot was not copied",
                    message = """
                            {
                                "sender": "Sender Name  <%s>",
                                "recipient":"%s",
                                "aws_region":"%s",
                                "body": "The copy process of the snapshot %s has failed."
                            }
                            """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION, copy_name)
                )
                continue
        
            i = i + 1
            # if 5 snapshots are already being copied, it returns the number of snapshots left to copy. 
            if i == copy_limit:
                break
    
    info["SnapshotsBeingCopied"] = i
    info["SnapshotsRemaining"] = n - i
    return info
      
def delete_old_snapshots(snapshots, snap_type):
    pattern = re.compile("^sc-")
    response = CLIENT_DB_DEST.describe_db_snapshots(
        IncludeShared=False,
        IncludePublic=False,
    )

    if len(response['DBSnapshots']) == 0:
        raise Exception("No snapshots in second region found")
    
    snapshots_per_database = {}
    
    for snapshot in response['DBSnapshots']:
        if snapshot['Status'] != 'available':
            continue

        # Test if the snapshot name matches the pattern of automatically copied snapshots
        test_match = pattern.match(snapshot['DBSnapshotIdentifier'])
        if test_match == None:
            continue
        
        delete_time = datetime.datetime.now() - datetime.timedelta(seconds=RETENTION_TIME)
        snapshot_start_time = snapshot['SnapshotCreateTime'].replace(tzinfo=None)
        delete_time = delete_time.replace(tzinfo=None)
        
        if snapshot_start_time < delete_time:
            print("Processing deletion of snapshot " + snapshot['DBSnapshotIdentifier'])
            CLIENT_DB_DEST.delete_db_snapshot(
                DBSnapshotIdentifier=snapshot['DBSnapshotIdentifier']
            )
            

def lambda_handler(event, context):
    
    ####################Deletion########################
    snapshots_manual = get_snapshots(CLIENT_DB_SOURCE, "manual")
    delete_old_snapshots(snapshots_manual, "manual")
    snapshots_automated = get_snapshots(CLIENT_DB_SOURCE, "automated")
    delete_old_snapshots(snapshots_automated, "automated")
    ####################################################
    
    nb_copy = get_nb_copy(CLIENT_DB_DEST)
    copy_limit = 5 - nb_copy
    if (copy_limit <= 0):
        exit(0)

    ####################Copy Manual#####################
    snapshots_manual = get_snapshots(CLIENT_DB_SOURCE, "manual")
    info = launch_copy_snapshots(snapshots_manual, "manual", copy_limit)
    ####################################################
    
    copy_limit = copy_limit - info["SnapshotsBeingCopied"] 
    if (copy_limit <= 0):
        exit(0)

    ###################Copy Auto########################
    snapshots_automated = get_snapshots(CLIENT_DB_SOURCE, "automated")
    info = launch_copy_snapshots(snapshots_automated, "automated", copy_limit)
    ####################################################
    
    if copy_limit == 5 - nb_copy:
        events_client = boto3.client('events')
        response = events_client.disable_rule(
            Name="{0}-Trigger".format(context.function_name)
        )
        print ("Rule disabled. No more snapshots to copy")
        send_email(
                subject = "Rds Snapshot Copy finished",
                message = """
                    {
                        "sender": "Sender Name  <%s>",
                        "recipient":"%s",
                        "aws_region":"%s",
                        "body": "The copy process of RDS snapshots has just ended."
                    }
                """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION)
        )
        exit(0)