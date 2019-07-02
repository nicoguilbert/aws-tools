################################################################
# This script copies every snapshot from us-west-2 to us-west-1
# Python 3.7
################################################################

import boto3
import time
import re
from datetime import datetime, timedelta, timezone


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
# Original function (lots of typos and errors, basically not working)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################

class Ec2Instances(object):
    
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

    def sort(self):
        self.snapshots.sort(key=lambda r:r.start_time, reverse=True)

    def get_nb_copy(self):
        response = self.ec2_dest.describe_snapshots(
            Filters=[{ 'Name': 'status', 'Values': ['pending', 'creating' ] }],
            OwnerIds=[ 
                self.aws_account, 
            ],
        )
        return len(response["Snapshots"])

    def get_snapshots(self):
        response = self.ec2_source.describe_snapshots(
            Filters=[{ 'Name': 'status', 'Values': ['completed']}],
            OwnerIds=[
                self.aws_account,
            ],
        )
        return response["Snapshots"]

    def set_snapshots(self):
        n = 0
        snapshots = self.get_snapshots()       
        
        for snapshot in snapshots:
            s = EBSSnapshot(snapshot["SnapshotId"], self.region_source)
            already_copied = s.filter_snapshot()        
        
            if already_copied == False:
                self.snapshots.append(s)
                n = n + 1

        self.sort()
        print(str(n) + " EBS snapshots to copy from " + self.region_source)
        return n
    
    def copy_snapshot(self, old_snapshot):
        print ("Started copying.. snapshot_id: " + old_snapshot.id + ", from: " + self.region_source + ", to: " + self.region_dest)

        try:
            copy_response = self.ec2_dest.copy_snapshot(
                Description = old_snapshot.new_snapshot_description,
                SourceRegion = self.region_source,
                SourceSnapshotId = old_snapshot.id,
                DryRun=False
            )
            new_id = copy_response["SnapshotId"]
            ec2_resource = boto3.resource('ec2')
            new_s = EBSSnapshot(new_id, self.region_dest, True)
            new_s.copy_update_tags(old_snapshot)
            return new_s.id

        except Exception as err:
            self.handle_error(
                email_subject="EBS Snapshot copy failed"
                resource_type="EBS Snapshot", 
                resource_info=old_snapshot.id, 
                region=self.region_source, 
                action= "Copy cross region", 
                error=err
            )

    def copy_snapshots(self, copy_limit):
        n = 0
        for s in self.snapshots:
            new_id = self.copy_snapshot(s)
            print("Snapshot " + str(s.id) + " successfully copied to snapshot " + str(new_id))
            n = n + 1
            if n == copy_limit:
                break
        return n

class EBSSnapshot(object):

    def __init__(self, snapshot_id, region_source, just_created = False, region_dest = None):
        self.ec2_resource = boto3.resource('ec2')
        self.ec2 = boto3.client('ec2', region_name = region_source)
        self.region_source = region_source
        self.snapshot_client = self.ec2_resource.Snapshot(snapshot_id) 
        self.id = snapshot_id
        if just_created == False:
            self.volume_id = self.snapshot_client.volume_id
            self.description = self.snapshot_client.description
            self.start_time = self.snapshot_client.start_time
            self.tags = self.snapshot_client.tags
        else:
            self.volume_id = ""
            self.description = ""
            self.start_time = ""
            self.tags = ""
        self.name = ""
        self.instance_name = ""
        self.new_snapshot_description = ""
        if region_source != None:
            self.region_source = region_source
        if region_dest != None:
            self.region_dest = region_dest

    def create_tag(self, key, value):
        print ("Creating tag - " + key + ":" + value + ", snapshot_id: " + str(self.id))
        self.ec2.create_tags(
            Resources=[ self.id ], 
            Tags=[{'Key': key, 'Value':value},] 
        )
        self.tags.append({'Key': key, 'Value':value})

    def delete_tag(self, key, value):
        print ("Deleting tag - " + key + ":" + value + ", snapshot_id: " + str(self.id))
        self.ec2.delete_tags(
            Resources=[ self.id ], 
            Tags=[{'Key': key, 'Value':value},] 
        )
        self.tags = [t for t in self.tags if not (t['Key'] == key and t['Value'] == value)]

    def set_tags(self):
        if self.tags == []:
            self.create_tag("BackupCrossRegion", "Waiting")
        
        if (next((item for item in self.tags if item['Key'] == 'BackupCrossRegion'), False) == False):
                self.create_tag('BackupCrossRegion', 'Waiting')
    
    def copy_tags(self, tags):
        tag = self.ec2.create_tags(
                Resources=[ str(self.id) ],
                Tags=tags
            )
        return tag

    def copy_update_tags(self, old_snapshot):
        #Copying tags from original snapshot to new snapshot
        try:
            tag = self.copy_tags(old_snapshot.tags)
        except:
            self.create_tag('IssueWithTags', 'Colon')
            print ("This snapshot might contain tags starting by 'aws:'. No way to handle them.")
            print (self.id)
        
        # if there was a tag "Name"
        if old_snapshot.name != "NameUndefined":
            self.delete_tag('Name', self.name)
        # if the value of the tag "Name" was empty
        if old_snapshot.name == "":
            self.name = "NameEmpty"
    
        copy_name = "sc-" + old_snapshot.name + "-" + old_snapshot.start_time.strftime("%Y-%m-%d")
    
        self.create_tag('Name', copy_name)
        self.create_tag('SnapshotType', 'AutomatedCopyCrossRegion')
        self.create_tag('OriginalSnapshotID', old_snapshot.id)
    
        print("Successfully copyied.. snapshot_id: " + old_snapshot.id + ", from: " + old_snapshot.region_source + ", to: " + self.region_source)
    
        old_snapshot.delete_tag('BackupCrossRegion', 'Waiting')
        old_snapshot.create_tag('BackupCrossRegion', 'Done')

        return self.id

    def filter_snapshot(self):
        pattern = re.compile("^sc-")
        
        self.set_snapshot_name()
        
        test_match = pattern.match(self.name)
        if test_match != None:
            return True
    
        self.set_tags()
        
        for t in self.tags:
            # If the snapshot has already been copied
            if t['Key'] == 'BackupCrossRegion' and t['Value'] == 'Done':
                return True
        
        self.set_new_snapshot_description()
        return False
    
    def get_volume_attachments(self, volume_id):
        try:
            response = self.ec2_source.describe_volumes( 
                VolumeIds=[ volume_id, ],
            )
            volume = ec2_source.Volume(volume_id)
            return volume.attachments
        except:
            print ("The volume '" + volume_id + "' cannot be found. Must have been deleted.")
            return False

    def set_instance_name(self, instance_id):
        instance = ec2_source.Instance(instance_id)
        
        for tag in instance.tags:
            if tag["Key"] == "Name":
                self.instance_name = tag["Value"]

        self.instance_name = "NameUndefined"
        return self.instance_name

    def set_snapshot_name(self):
        self.name = "NameUndefined"
        for tag in self.tags:
            if tag["Key"] == "Name":
                self.name = tag["Value"]
        return self.name
        
    def set_new_snapshot_description(self):
        new_description = ""
        
        if self.volume_id == "vol-ffffffff":
            new_description = "This snapshot was a copy of another.. "
        else: 
            # Puts a list in attachments. The list only contains one element
            # Or contains a string
            attachments = self.get_volume_attachments(self.volume_id)
            if attachments == False:
                new_description = "Volume did not exist. Could not find attachements."
            elif attachments == []:
                new_description = new_description + "Volume not attached/deleted." + " RegionSource: " + region_source
            else:
                # Puts a dictionnary containing the volume informations inside volume_dict
                volume_dict = attachments[0]
                instance_name = "Ec2Name: " + self.set_instance_name(volume_dict["InstanceId"])
                block_device = ", BlockDevice: " + volume_dict["Device"]
                new_description = new_description + instance_name + block_device + ", RegionSource: " + region_source

        self.new_snapshot_description = new_description
            
def lambda_handler(event, context):
    nb_copy_processing = 0
    nb_to_copy = 0
    total_to_copy = 0
    i = 0
    ec2 = []

    # Loop for collecting the snapshots to copy and some information
    for region in REGIONS:
        o_ec2 = Ec2Instances(region["Source"], region["Destination"])
        nb_copy_processing = nb_copy_processing + o_ec2.get_nb_copy()

        if nb_copy_processing >= 5:
            print("Already 5 snapshots being copied. Waiting for the next call.")
            return 0

        nb_to_copy = o_ec2.set_snapshots()
        if nb_to_copy > 0:
            ec2.append(o_ec2)
            total_to_copy = total_to_copy + nb_to_copy
            #print(ec2[i].get_nb_copy())
            i = i + 1

        if total_to_copy >= 5 - nb_copy_processing:
            break

    # If there's no snapshots to copy, destroy the CW event.
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

    for n in range(0, i):
        if copy_limit <= 0:
            break

        nb_copied = ec2[n].copy_snapshots(copy_limit)
        print(str(nb_copied) + " snapshots copied")
        copy_limit = copy_limit - nb_copied
    


    
