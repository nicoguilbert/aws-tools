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

######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
######################################################################################
# Original function (lot of typos like double quotes missing)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################

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
        
        copy_name = get_copy_name(database, snapshot_name, start_time)
        if self.already_copied(copy_name) == False:
            self.snapshots.append((database, snapshot_name, start_time))
            n = n + 1

        self.sort()
        print(str(n) + " RDS snapshots to copy in " + self.region_source)
        return n

    
    def copy_snapshot(self, snapshot, copy_name):
        response = self.client_db_dest.copy_db_snapshot(
            SourceDBSnapshotIdentifier='arn:aws:rds:' + self.region_source + ':' + self.aws_account + ':snapshot:' + snapshot[1],
            TargetDBSnapshotIdentifier=copy_name,
            CopyTags=True
        )
        return response

    def copy_snapshots(self, copy_limit):    
        #nb_to_copy = self.set_db_snapshots()
        
        n = 0
    
        for s in self.snapshots:
            copy_name = self.get_copy_name(s[0], s[1], s[2])
            response = self.copy_snapshot(s, copy_name)

            if response['DBSnapshot']['Status'] != "pending" and response['DBSnapshot']['Status'] != "available":
                raise Exception("Copy operation for " + copy_name + " failed!")               
                
                self.send_email(
                    subject = "An Rds Snapshot was not copied",
                    message = """
                            {
                                "sender": "Sender Name  <%s>",
                                "recipient": "%s",
                                "aws_region": "%s",
                                "body": "The copy process of the snapshot %s has failed."
                            }
                            """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION, copy_name)
                )
                continue
        
            n = n + 1
            # if 5 snapshots are already being copied, it returns the number of snapshots left to copy. 
            if n == copy_limit:
                break
        return n

    def get_delete_time(self, older_days):
        delete_time = datetime.datetime.now() - datetime.timedelta(seconds=RETENTION_TIME)
        delete_time = delete_time.replace(tzinfo=None)
        return delete_time

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

            start_time = snapshot['SnapshotCreateTime'].replace(tzinfo=None)
            if start_time < delete_time:
                print("Processing deletion of snapshot " + snapshot['DBSnapshotIdentifier'])
                self.delete_snapshot(snapshot['DBSnapshotIdentifier'])
                n = n + 1

        print(str(n) + " RDS snapshots deleted on region " + self.region_dest)
        return n
        
def lambda_handler(event, context):
    nb_copy_processing = 0
    nb_to_copy = 0
    total_to_copy = 0
    i = 0
    rds = []

    for region in REGIONS:
        o_rds_manual = RdsDB(region["Source"], region["Destination"], "manual")

        nb_copy_processing = nb_copy_processing + o_rds_manual.get_nb_copy()
        if nb_copy_processing >= 5:
            print("Already 5 snapshots being copied. Waiting for the next call.")
            return 0

        nb_to_copy = o_rds_manual.set_snapshots()
        if nb_to_copy > 0:
            rds.append(o_rds_manual)
            total_to_copy = total_to_copy + nb_to_copy
            i = i + 1

        if total_to_copy >= 5 - nb_copy_processing:
            break

        o_rds_auto = RdsDB(region["Source"], region["Destination"], "automated")

        nb_copy_processing = nb_copy_processing + o_rds_auto.get_nb_copy()
        if nb_copy_processing >= 5:
            print("Already 5 snapshots being copied. Waiting for the next call.")
            return 0

        nb_to_copy = o_rds_auto.set_snapshots()
        if nb_to_copy > 0:
            rds.append(o_rds_auto)
            total_to_copy = total_to_copy + nb_to_copy
            i = i + 1

        if total_to_copy >= 5 - nb_copy_processing:
            break

    if total_to_copy == 0:
        events_client = boto3.client('events') 
        events_client.remove_targets( 
            Rule="{0}-Trigger".format(context.function_name), 
            Ids=[ 
                '1', 
            ] 
        ) 
        events_client.delete_rule( 
            Name="{0}-Trigger".format(context.function_name) 
        )

    copy_limit = 5 - nb_copy_processing

    for n in range (0, i):
        if copy_limit <= 0:
            break

        nb_copied = rds[n].copy_snapshots(copy_limit)
        print(str(nb_copied) + " snapshots copied")

        copy_limit = copy_limit - nb_copied
        rds[n].delete_snapshots(DAYS_OF_RETENTION)
