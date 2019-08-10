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

KMS_KEY_ALIAS = "alias/aws/rds"

COPY_DEFINITIONS = [
    {
        "Source" : "us-east-2",
        "Destination" : "us-east-1"
    }#,
    #{
    #   "Source" : "us-west-2",
    #   "Destination" : "us-west-1"
    #}#,
    # etcetera
]

ACCOUNT = "728679744102"

#SysAdmin-AWS@doxcelerate.com
EMAIL_SENDER = "SysAdmin-AWS@doxcelerate.com"
EMAIL_RECIPIENT = "SysAdmin-AWS@doxcelerate.com"
EMAIL_REGION = "us-east-1"
TOPIC_ARN = "arn:aws:sns:us-east-1:728679744102:EmailsToSend"

SNS = boto3.resource('sns')
EMAIL_TOPIC = SNS.Topic(TOPIC_ARN)

######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/rds.html
######################################################################################
# Original function (lot of typos like double quotes missing)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################

# Global functions
def delete_rule(context):
        events_client = boto3.client('events') 
        lambda_client = boto3.client('lambda')

        lambda_client.remove_permission(
            FunctionName=context.function_name,
            StatementId="{0}-Event".format(context.function_name)
        )

        events_client.remove_targets( 
            Rule="{0}-Trigger".format(context.function_name), 
            Ids=[ 
                '2', 
            ] 
        ) 
        events_client.delete_rule( 
            Name="{0}-Trigger".format(context.function_name) 
        )

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
        message = r"""
            {
                "sender": "%s",
                "recipient":"%s",
                "aws_region":"%s",
                "body": "Resource Type : %s  \nResource : %s  \nRegion : %s  \nAction : %s  \nError : %s"
            }
        """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION, resource_type, resource_info, region, action, error)
    )
    print("DOX-ERROR : Resource Type : %s .Resource Id : %s . Region : %s . Process : %s . Error : %s" % (resource_type, resource_info, region, action, error))


class RdsWorkUnit(object):
    ''' This class represents a work unit for processing the copy of the snapshots on various regions.
    '''

    def __init__(self, region_source, region_dest, snap_type):
        self.region_source = region_source
        self.region_dest = region_dest
        self.snap_type = snap_type

        self.client_db_source = boto3.client("rds", region_name=self.region_source)
        self.client_db_dest = boto3.client("rds", region_name=self.region_dest)

        self.snapshots_list = []
        self.init_snapshots_list()


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
        self.snapshots_list.sort(key=lambda r:r["SnapshotCreateTime"], reverse=True)
        #print("### List sorted.")

    def get_snapshots_to_copy(self):
        # DOES NOT WORK FOR AURORA ! ! ! 
        response = self.client_db_source.describe_db_snapshots(
            SnapshotType=self.snap_type,
            IncludeShared=False,
            IncludePublic=False
        )
        return response['DBSnapshots']

    def get_copy_name(self, snapshot):
        if self.snap_type == "automated":
            # snapshot[0] = database name
            copy_name = "sc-" + snapshot["DBInstanceIdentifier"] + "-" + snapshot["SnapshotCreateTime"].strftime("%Y-%m-%d-%Hh%Mm")
        elif self.snap_type == "manual":
            # snapshot[1] = original manual snapshot name
            copy_name = "sc-" + snapshot["DBSnapshotIdentifier"] + "-" + snapshot["SnapshotCreateTime"].strftime("%Y-%m-%d-%Hh%Mm")
        else:
            copy_name = "sc-Undefined-" + snapshot["SnapshotCreateTime"].strftime("%Y-%m-%d-%Hh%Mm")

        return copy_name

    # Returns False if the snapshot has to be copied.
    # Returns True if the snapshot has been copied OR if it is already a copy itself
    def is_copied(self, snapshot_name, copy_name):
        #print("Checking if " + copy_name + " already exists.")
        pattern = re.compile("^sc-")

        test_match = pattern.match(snapshot_name)
        if test_match != None:
            #print("Already a copy. Not copying.")
            return True

        try:
            self.client_db_dest.describe_db_snapshots(
                DBSnapshotIdentifier=copy_name
            )
            #print("Already Exists. Not copying.")

            return True

        except botocore.exceptions.ClientError as err:
            if err.response['Error']['Code'] == "DBSnapshotNotFound":
                return False

            else:
                print(err)
                handle_error( email_subject="Error while checking if a snapshot exists.", resource_type="RDS Snapshot", resource_info=copy_name, region=self.region_source, action= "Describe DB snapshot",  error=str(err) )
                return True

        except Exception as err:
            print(err)
            handle_error( email_subject="Error while checking if a snapshot exists.", resource_type="RDS Snapshot", resource_info=copy_name, region=self.region_source, action= "Describe DB snapshot",  error=str(err) )
            return True
    
    ###################################################################
    # Naming rule for the new snapshot :
    # Automated => Name of database + Creation date (year-month-day-h-m)
    # Manual    => Name of the snapshot + Creation date 
    ###################################################################

    def init_snapshots_list(self):
        nb_snapshots_to_copy = 0
        snapshots = self.get_snapshots_to_copy()

        for snapshot in snapshots:
            if snapshot['Status'] != 'available':
                continue
            
            copy_name = self.get_copy_name(snapshot)
            
            if self.is_copied(snapshot["DBSnapshotIdentifier"], copy_name) == False:
                self.snapshots_list.append(snapshot)
                nb_snapshots_to_copy = nb_snapshots_to_copy + 1

        self.sort_snapshots_by_time()

        print("DOX-START : " + str(nb_snapshots_to_copy) + " RDS " + self.snap_type + " snapshots to copy in " + self.region_source)
        #return nb_snapshots_to_copy

    def copy_snapshot(self, snapshot, copy_name):
        print("DOX-START : copying " + snapshot["DBSnapshotIdentifier"])
        try:
            is_encrypted = snapshot["Encrypted"]

            # if the snapshot is encrypted
            if is_encrypted:
                kms_client = boto3.client('kms', region_name=self.region_dest)
                kms_key = kms_client.describe_key( KeyId = KMS_KEY_ALIAS )
                #print(kms_key)
                #https://github.com/boto/boto3/issues/960
                
                response = self.client_db_dest.copy_db_snapshot(
                    SourceDBSnapshotIdentifier='arn:aws:rds:' + self.region_source + ':' + ACCOUNT + ':snapshot:' + snapshot["DBSnapshotIdentifier"],
                    TargetDBSnapshotIdentifier=copy_name,
                    CopyTags=True,
                    KmsKeyId=kms_key["KeyMetadata"]["Arn"],
                    SourceRegion=self.region_source
                )

            # if the snapshot is not encrypted
            else:
                response = self.client_db_dest.copy_db_snapshot(
                    SourceDBSnapshotIdentifier='arn:aws:rds:' + self.region_source + ':' + ACCOUNT + ':snapshot:' + snapshot["DBSnapshotIdentifier"],
                    TargetDBSnapshotIdentifier=copy_name,
                    CopyTags=True
                )

            print("DOX-SUCCESS : " + snapshot["DBSnapshotIdentifier"] + " successfully copied." )
            return response

        except botocore.exceptions.ClientError as err:
            if err.response['Error']['Code'] == "SnapshotQuotaExceeded":
                print(err)
                raise err
            else:
                print(err)
                handle_error( email_subject="RDS Snapshot copy failed", resource_type="RDS Snapshot", resource_info=copy_name, region=self.region_source, action= "Copy cross region",  error=str(err) )

        except Exception as err:
            print(err)
            handle_error( email_subject="RDS Snapshot copy failed", resource_type="RDS Snapshot", resource_info=copy_name, region=self.region_source, action= "Copy cross region",  error=str(err) )

    def copy_snapshots(self):    
        nb_snapshots_copied = 0
        
        try:
            for snapshot in self.snapshots_list:
                copy_name = self.get_copy_name(snapshot)
                copy_response = self.copy_snapshot(snapshot, copy_name)
            
                nb_snapshots_copied = nb_snapshots_copied + 1
                self.add_tag_to_snapshot("OriginalSnapshotID", snapshot["DBSnapshotIdentifier"], copy_response["DBSnapshot"]["DBSnapshotArn"])
                self.add_tag_to_snapshot("DBInstanceClass", self.get_instance_size(snapshot), copy_response["DBSnapshot"]["DBSnapshotArn"])

        except:
            print("DOX-RESULT: " + str(nb_snapshots_copied) + " snapshots copied.")
        return True

    # Returns the instance type/size (db.t2.micro or something like that)
    def get_instance_size(self, snapshot):
        db_response = self.client_db_source.describe_db_instances(DBInstanceIdentifier = snapshot["DBInstanceIdentifier"])
        return db_response["DBInstances"][0]["DBInstanceClass"]

def lambda_handler(event, context):
    delete_rule_flag = True

    for copy_definition in COPY_DEFINITIONS:
        ####################
        # manual snapshots #
        #################### 
        try:
            manual_work_unit = RdsWorkUnit(copy_definition["Source"], copy_definition["Destination"], "manual")
            copy_response = manual_work_unit.copy_snapshots()

        # If there's more snapshots to copy, do not delete the rule
        # Here the exception is the Snapshot Copy Limit is reached.
        except Exception as err:
            print(err)
            delete_rule_flag = False

        #######################
        # automated snapshots #
        #######################
        try:
            automated_work_unit = RdsWorkUnit(copy_definition["Source"], copy_definition["Destination"], "automated")
            copy_response = automated_work_unit.copy_snapshots()

        except Exception as err:
            print(err)
            delete_rule_flag = False

    # If there's nothing to copy, it deletes the cloudwatch rule
    if delete_rule_flag == True:
        delete_rule(context)

