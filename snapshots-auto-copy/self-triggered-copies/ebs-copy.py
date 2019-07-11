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
        "Source" : "us-west-1",
        "Destination" : "us-west-2"
    }#,
    #{
    #   "Source" : "us-west-2",
    #   "Destination" : "us-west-1"
    #}#,
    # etcetera
]

ACCOUNT = "728679744102"

# How many days do you want to keep the snapshots
DAYS_OF_RETENTION = 14

EMAIL_SENDER = "nicolasguilbert.tours@gmail.com"
EMAIL_RECIPIENT = "nicolasguilbert.tours@gmail.com"
EMAIL_REGION = "us-west-2"
TOPIC_ARN = "arn:aws:sns:us-west-1:728679744102:EmailsToSend"

######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
######################################################################################
# Original function (lots of typos and errors, basically it's not working)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################

def delete_rule(context):
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
        
class EC2WorkUnit(object):
    ''' This class represents a work unit for processing the copy of the snapshots on various regions.
    '''

    def __init__(self, region_source, region_dest):
        self.region_source = region_source
        self.region_dest = region_dest

        self.aws_account = ACCOUNT
        self.email_sender = EMAIL_SENDER
        self.email_recipient = EMAIL_RECIPIENT
        self.email_region = EMAIL_REGION

        self.ec2_source = boto3.client('ec2', region_name=region_source)
        self.ec2_dest = boto3.client('ec2', region_name=region_dest)
        self.ec2_resource = boto3.resource('ec2')
        self.sns = boto3.resource('sns')
        self.email_topic = self.sns.Topic(TOPIC_ARN)
        
        self.snapshots = []
        self.init_snapshots_list()

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

    def sort_snapshots_by_time(self, snapshots):
        snapshots.sort(key=lambda r:r["StartTime"] , reverse=True)
        return snapshots

    def get_snapshots_on_region_source(self):
        response = self.ec2_source.describe_snapshots(
            Filters=[{ 'Name': 'status', 'Values': ['completed']}],
            OwnerIds=[
                self.aws_account,
            ],
        )
        return response["Snapshots"]

    def init_snapshots_list(self):
        nb_snapshot_to_copy = 0
        snapshots = self.get_snapshots_on_region_source()       
        snapshots_sorted = self.sort_snapshots_by_time(snapshots)

        for snapshot in snapshots_sorted:
            #start = time.time()
            s = MyEbsSnapshot(snapshot["SnapshotId"], self.region_source)
            #end = time.time()
            #print(s.id)
            #print(end - start)        
            if s.is_copied == False:
                self.snapshots.append(s)
                nb_snapshot_to_copy = nb_snapshot_to_copy + 1
            if nb_snapshot_to_copy == 5:
                break

        print(str(nb_snapshot_to_copy) + " EBS snapshots about to be copied from " + self.region_source)
        return nb_snapshot_to_copy
    
    # Returns the id of the snapshot just created
    def copy_snapshot(self, old_snapshot):
        print ("Started copying.. snapshot_id: " + old_snapshot.id + ", from: " + self.region_source + ", to: " + self.region_dest)

        try:
            copy_response = self.ec2_dest.copy_snapshot(
                Description = old_snapshot.get_new_snapshot_description(),
                SourceRegion = self.region_source,
                SourceSnapshotId = old_snapshot.id,
                DryRun=False
            )
            new_id = copy_response["SnapshotId"]
            ec2_resource = boto3.resource('ec2')
            new_snapshot = MyEbsSnapshot(new_id, self.region_dest)
            new_snapshot.copy_tags_from_old(old_snapshot)
            return new_snapshot.id

        except botocore.exceptions.ClientError as err:
            print("5 SNAPSHOTS LIMIT REACHED. " + str(err)) 
            return "CopyLimitException"

        except Exception as err:
            self.handle_error(
                email_subject="EBS Snapshot copy failed",
                resource_type="EBS Snapshot", 
                resource_info=old_snapshot.id, 
                region=self.region_source,  
                action= "Copy cross region", 
                error=err
            )
            print(err)
            return "Error"

    def copy_snapshots(self):
        nb_snapshots_copied = 0

        for snapshot in self.snapshots:
            copy_response = self.copy_snapshot(snapshot)

            if copy_response == "CopyLimitException":
                print("Copy limit exception catched. Interruption.")
                return copy_response

            elif copy_response == "Error":
                print("An error occured.")
                continue

            else:
                print("Snapshot " + str(snapshot.id) + " successfully copied to snapshot " + str(copy_response))
                nb_snapshots_copied = nb_snapshots_copied + 1

        print("No more snapshots to copy on " + self.region_source) 
        return 0

class MyEbsSnapshot(object):
    ''' This class is an extension of the boto3 Snapshot class allowing actions on these snapshots on AWS
    '''

    def __init__(self, snapshot_id, region, just_created = False):
        self.ec2_resource = boto3.resource('ec2')
        self.ec2_client = boto3.client('ec2', region_name = region)
        self.region = region
        self.aws_snapshot_interface = self.ec2_resource.Snapshot(snapshot_id) 
        self.id = snapshot_id
        
        self.tags = []
        self.init_tags()

        self.snapshot_name = ""
        self.init_snapshot_name()

        self.is_copied = self.is_copied()

        self.start_time = ""
        self.volume_id = ""

        if self.is_copied == False:
            self.init_start_time()
            self.init_volume_id()

    def create_tag(self, key, value):
        print ("Creating tag - " + key + ":" + value + ", snapshot_id: " + str(self.id))
        self.ec2_client.create_tags(
            Resources=[ self.id ], 
            Tags=[{'Key': key, 'Value':value},] 
        )
        # Updates tags attribute
        self.tags.append({'Key': key, 'Value':value})

    def delete_tag(self, key, value):
        print ("Deleting tag - " + key + ":" + value + ", snapshot_id: " + str(self.id))
        self.ec2_client.delete_tags(
            Resources=[ self.id ], 
            Tags=[{'Key': key, 'Value':value},] 
        )
        # Updates tags attribute
        self.tags = [t for t in self.tags if not (t['Key'] == key and t['Value'] == value)]

    def init_snapshot_name(self):
        name = ""
        try:
            for tag in self.tags:
                if tag["Key"] == "Name":
                    name = tag["Value"]
        except Exception as err:
            print(err + " - tag issue")
            name = "NameUndefined"
        if name == "":
            name = "Ec2Name404"
        self.snapshot_name = name

    def init_tags(self):
        try:
            self.tags = self.tags + self.aws_snapshot_interface.tags
        except Exception as err:
            print("init_tags() error :")
            print(err)

        if self.tags == []:
            self.create_tag("BackupCrossRegion", "Waiting")
        
        if (next((item for item in self.tags if item['Key'] == 'BackupCrossRegion'), False) == False):
            self.create_tag('BackupCrossRegion', 'Waiting')
    
    def init_start_time(self):
        try:
            self.start_time = self.aws_snapshot_interface.start_time
        except:
            print("init_start_time() error. No problem.")
            #if start_time is unavailable, we init it with current time
            self.start_time = datetime.now().strftime("%Y-%m-%d-%Hh%Mm")
        
        #return self.start_time
    
    def init_volume_id(self):
        try:
            self.volume_id = self.aws_snapshot_interface.volume_id
        except:
            print("init_volume_id() error. No problem.")
            self.volume_id = "VolumeID not available."
        
        #return self.volume_id

    def add_tags(self, tags):
        response_tags = self.ec2_client.create_tags(
                Resources=[ str(self.id) ],
                Tags=tags
            )
        return response_tags

    def copy_tags_from_old(self, old_snapshot):
        #Copying tags from original snapshot to new snapshot
        try:
            tag = self.add_tags(old_snapshot.tags)
        except:
            self.create_tag('IssueWithTags', 'Colon')
            print ("This snapshot might contain tags starting by 'aws:'. No way to handle them.")
            print (self.id)
        
        # if there was a tag "Name"
        if old_snapshot.snapshot_name != "NameUndefined":
            self.delete_tag('Name', self.snapshot_name)
        # if the value of the tag "Name" was empty
        if old_snapshot.snapshot_name == "":
            self.snapshot_name = "NameEmpty"
    
        copy_name = "sc-" + old_snapshot.snapshot_name + "-" + old_snapshot.start_time.strftime("%Y-%m-%d-%Hh%Mm")
    
        self.create_tag('Name', copy_name)
        self.create_tag('SnapshotType', 'AutomatedCopyCrossRegion')
        self.create_tag('OriginalSnapshotID', old_snapshot.id)
    
        print("Successfully copyied.. snapshot_id: " + old_snapshot.id + ", from: " + old_snapshot.region + ", to: " + self.region)
    
        old_snapshot.delete_tag('BackupCrossRegion', 'Waiting')
        old_snapshot.create_tag('BackupCrossRegion', 'Done')

        return self.id

    def is_copied(self):
        pattern = re.compile("^sc-")
                
        test_match = pattern.match(self.snapshot_name)
        if test_match != None:
            return True
        
        for t in self.tags:
            # If the snapshot has already been copied
            if t['Key'] == 'BackupCrossRegion' and t['Value'] == 'Done':
                return True
        
        return False
    
    def get_snapshot_description(self):
        try:
            description = self.aws_snapshot_interface.description
        except:
            description = "Snapshot Description not found."
        return description

    def get_volume_attachments(self, volume_id):
        try:
            response = self.ec2_client.describe_volumes( 
                VolumeIds=[ volume_id, ],
            )
            volume = self.ec2_resource.Volume(volume_id)
            return volume.attachments
        except Exception as err:
            print(err)
            print ("The volume " + volume_id + " cannot be found. Must have been deleted.")
            return False

    def get_instance_name(self, instance_id):
        instance = self.ec2_resource.Instance(instance_id)
        instance_name = ""

        for tag in instance.tags:
            if tag["Key"] == "Name":
                instance_name = tag["Value"]

        if instance_name == "":
            instance_name = "Ec2NameUndefined"

        return instance_name
        
    def get_new_snapshot_description(self):
        new_description = ""
        
        if self.volume_id == "vol-ffffffff":
            new_description = "Couldn't find attachements."
        else: 
            # Puts a list in attachments. The list only contains one element
            # Or contains a string
            attachments = self.get_volume_attachments(self.volume_id)
            if attachments == False:
                new_description = "Volume did not exist. Could not find attachements."
            elif attachments == []:
                new_description = new_description + "Volume not attached/deleted." + " RegionSource: " + self.region
            else:
                # Puts a dictionnary containing the volume informations inside volume_dict
                volume_dict = attachments[0]
                instance_name = "Ec2Name: " + self.get_instance_name(volume_dict["InstanceId"])
                block_device = ", BlockDevice: " + volume_dict["Device"]
                new_description = new_description + instance_name + block_device + ", RegionSource: " + self.region

        return new_description
            
def lambda_handler(event, context):
    delete_rule_flag = True

    for copy_order in COPY_DEFINITIONS:
        work_unit = EC2WorkUnit(copy_order["Source"], copy_order["Destination"])
        
        work_unit.init_snapshots_list()
        copy_response = work_unit.copy_snapshots()
        #print(copy_response)

        if copy_response == "CopyLimitException":
            delete_rule_flag = False

    if delete_rule_flag == True:
        delete_rule(context)






