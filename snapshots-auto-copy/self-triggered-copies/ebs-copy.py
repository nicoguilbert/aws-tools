################################################################
# This script copies every snapshot from us-west-2 to us-west-1
# Python 3.7
################################################################

import boto3
import time
import re
from datetime import datetime, timedelta, timezone
import botocore


######################
#  Global variables. #
######################

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

EC2_RESOURCE = boto3.resource('ec2')

SNS = boto3.resource('sns')
EMAIL_TOPIC = SNS.Topic(TOPIC_ARN)

######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
######################################################################################
# Original function (lots of typos and errors, basically it's not working)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################

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
                '1', 
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
                "sender": "Sender Name  <%s>",
                "recipient":"%s",
                "aws_region":"%s",
                "body": "Resource Type : %s \nResource : %s \nRegion : %s \nAction : %s \nError : %s"
            }
        """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION, resource_type, resource_info, region, action, error)
    )
    print("DOX-ERROR : Resource Type : %s . Resource Id : %s . Region : %s . Process : %s . Error : %s" % (resource_type, resource_info, region, action, error))

class EC2WorkUnit(object):
    ''' This class represents a work unit for processing the copy of the snapshots on various regions.
    '''

    def __init__(self, region_source, region_dest):
        self.region_source = region_source
        self.region_dest = region_dest

        self.ec2_source = boto3.client('ec2', region_name=region_source)
        self.ec2_dest = boto3.client('ec2', region_name=region_dest)
        
        self.snapshots = []
        self.init_snapshots_list()

    def sort_snapshots_by_time(self, snapshots):
        snapshots.sort(key=lambda r:r["StartTime"] , reverse=True)
        return snapshots

    def get_snapshots_on_region_source(self):
        # https://boto3.amazonaws.com/v1/documentation/api/1.9.42/reference/services/ec2.html#EC2.Client.describe_snapshots
        response = self.ec2_source.describe_snapshots(
            Filters=[{ 'Name': 'status', 'Values': ['completed']}],
            OwnerIds=[
                ACCOUNT,
            ],
        )
        return response["Snapshots"]

    def init_snapshots_list(self):
        nb_snapshot_to_copy = 0
        snapshots = self.get_snapshots_on_region_source()
        snapshots_sorted = self.sort_snapshots_by_time(snapshots)

        for snapshot in snapshots_sorted:
            if MyEbsSnapshot.is_copied(snapshot["SnapshotId"]) == False:
                s = MyEbsSnapshot(snapshot["SnapshotId"], self.region_source)
                self.snapshots.append(s)
                nb_snapshot_to_copy = nb_snapshot_to_copy + 1
            else:
                continue
                
            if nb_snapshot_to_copy == 10:
                break
            
        print("DOX-START : " + str(nb_snapshot_to_copy) + " EBS snapshots about to be copied from " + self.region_source)
        return nb_snapshot_to_copy
    
    # Returns the id of the snapshot just created
    def copy_snapshot(self, old_snapshot):

        try:
            print ("DOX-START: Copying.. snapshot_id: " + old_snapshot.id + ", from: " + self.region_source + ", to: " + self.region_dest)
            copy_response = self.ec2_dest.copy_snapshot(
                Description = old_snapshot.get_description_for_new_snapshot(),
                SourceRegion = self.region_source,
                SourceSnapshotId = old_snapshot.id,
                DryRun=False
            )
            new_id = copy_response["SnapshotId"]
            new_snapshot = MyEbsSnapshot(new_id, self.region_dest)
            new_snapshot.copy_tags_from_old(old_snapshot)
            print("DOX-SUCCESS: Snapshot " + str(old_snapshot.id) + " successfully copied")
            return True
        
        except botocore.exceptions.ClientError as e:
            # 5 snapshot limit reached
            if e.response['Error']['Code'] == "ResourceLimitExceeded":
                raise e
            # For every other clienterror 
            else:
                print(e)
                handle_error( email_subject="EBS Snapshot copy failed", resource_type="EBS Snapshot", resource_info=old_snapshot.id, region=self.region_source, action= "Copy cross region",  error=str(e) )
                return False

        except Exception as e:
            print(e)
            handle_error( email_subject="EBS Snapshot copy failed", resource_type="EBS Snapshot", resource_info=old_snapshot.id, region=self.region_source, action= "Copy cross region",  error=str(e) )
            return False

    def copy_snapshots(self):
        nb_snapshots_copied = 0

        for snapshot in self.snapshots:
            try:
                copy_response = self.copy_snapshot(snapshot)
                if copy_response == False:
                    continue
                nb_snapshots_copied = nb_snapshots_copied + 1
        
            except Exception as e:
                print("DOX-INFO: " + str(nb_snapshots_copied) + " snapshots copied")
                raise e

        print("DOX-INFO : " + str(nb_snapshots_copied) + " snapshots copied.")
        print("DOX-FINAL RESULT : No more snapshots to copy on " + self.region_source) 
        return 0

class MyEbsSnapshot(object):
    ''' This class is an extension of the boto3 Snapshot class allowing actions on these snapshots on AWS.
    '''

    def __init__(self, snapshot_id, region):
        self.ec2_client = boto3.client('ec2', region_name = region)
        self.region = region

        self.aws_snapshot_interface = EC2_RESOURCE.Snapshot(snapshot_id) 
        self.id = snapshot_id
        self.instance_name = ""

        self.init_tags()
        
    @staticmethod
    def is_copied(snapshot_id):
        pattern = re.compile("^sc-")

        snapshot = EC2_RESOURCE.Snapshot(snapshot_id) 
        try:
            for tag in snapshot.tags:
                # Checking if it is a destination snapshot (a copy)
                if tag['Key'] == 'Name':
                    test_match = pattern.match(tag['Value'])
                    if test_match != None:
                        return True
        
                # Checking if it is a source snapshot and if it has already been copied
                if tag['Key'] == 'BackupCrossRegion' and tag['Value'] == 'Done':
                    return True
        except:
            pass
        return False

    # init_tags() makes sure there is at least one tag 
    def init_tags(self):
        try:
            if self.aws_snapshot_interface.tags == []:
                self.create_tag("BackupCrossRegion", "Waiting")
            
            if (next((item for item in self.aws_snapshot_interface.tags if item['Key'] == 'BackupCrossRegion'), False) == False):
                self.create_tag('BackupCrossRegion', 'Waiting')
        
        except Exception as err:
            pass

    def create_tag(self, key, value):
        #print ("Creating tag - " + key + ":" + value + ", snapshot_id: " + str(self.id))
        self.ec2_client.create_tags(
            Resources=[ self.id ], 
            Tags=[{'Key': key, 'Value':value},] 
        )

    def delete_tag(self, key, value):
        #print ("Deleting tag - " + key + ":" + value + ", snapshot_id: " + str(self.id))
        self.ec2_client.delete_tags(
            Resources=[ self.id ], 
            Tags=[{'Key': key, 'Value':value},] 
        )
                    
    def copy_tags_from_old(self, old_snapshot):
        #Copying tags from original snapshot to new snapshot

        for tag in old_snapshot.aws_snapshot_interface.tags:
            try:
                self.create_tag(tag["Key"], tag["Value"])
            except:
                continue
    
        self.delete_tag('BackupCrossRegion', 'Waiting')

        copy_name = "sc-" + old_snapshot.instance_name + "-" + old_snapshot.aws_snapshot_interface.start_time.strftime("%Y-%m-%d-%Hh%Mm")
    
        self.create_tag('Name', copy_name)
        self.create_tag('SnapshotType', 'AutomatedCopyCrossRegion')
        self.create_tag('OriginalSnapshotID', old_snapshot.id)
    
        old_snapshot.delete_tag('BackupCrossRegion', 'Waiting')
        old_snapshot.create_tag('BackupCrossRegion', 'Done')

        return self.id
    
    def get_snapshot_description(self):
        try:
            description = self.aws_snapshot_interface.description
        except:
            description = "Snapshot Description not found."
        return description

    def get_volume_attachments(self, volume_id):
        response = self.ec2_client.describe_volumes( 
            VolumeIds=[ volume_id, ],
        )
        volume = EC2_RESOURCE.Volume(volume_id)
        if volume.attachments == []:
            attachments = []
            attachments[0] = {}
            attachments[0]["InstanceId"] = "Undefined"
            attachments[0]["Device"] = "NotFound"
        else:
            attachments = volume.attachments 
        return attachments

    def init_instance_name(self, instance=None):
        instance_name = ""
        try:
            for tag in instance.tags:
                if tag["Key"] == "Name":
                    instance_name = tag["Value"]
        except:
            instance_name = "Ec2NotFound"
        else:
            if instance_name == "":
                instance_name = "Ec2NameUndefined"

        self.instance_name = instance_name
    
    # Builds the description for the copy/new snapshot on destination region
    def get_description_for_new_snapshot(self):
        new_description = ""
        try:
            # If the volume_id is valid it will return information about the ec2
            # or initialize attachments with defaults values.
            attachments = self.get_volume_attachments(self.aws_snapshot_interface.volume_id)
        except:
            # default values if volume_id is not valid
            attachments = []
            attachments[0] = {}
            attachments[0]["InstanceId"] = "Undefined"
            attachments[0]["Device"] = "NotFound"
                
        #print(attachments)
        try:
            ec2_instance = EC2_RESOURCE.Instance(attachments[0]["InstanceId"])
        except:
            #init the instance name with a default value.
            self.instance_name = "Ec2NotFound"                
            ec2_instance_type = "NotFound"
        else:
            self.init_instance_name(ec2_instance)                
            ec2_instance_type = ec2_instance.instance_type

        new_description = new_description + "Ec2Name: " + self.instance_name + ", BlockDevice: " + attachments[0]["Device"] + ", InstanceType: " + ec2_instance_type

        #print(new_description)
        return new_description
            
def lambda_handler(event, context):
    # rule => CloudWatch Rule triggering this function every x minutes
    delete_rule_flag = True

    for copy_definition in COPY_DEFINITIONS:
        work_unit = EC2WorkUnit(copy_definition["Source"], copy_definition["Destination"])  
        
        try:
            copy_response = work_unit.copy_snapshots()

        except botocore.exceptions.ClientError as e:
            # If the limit of snapshot copies is reached :
            if e.response['Error']['Code'] == "ResourceLimitExceeded":
                delete_rule_flag = False

    if delete_rule_flag == True:
        delete_rule(context)
        print("DOX-Rule deleted.")
