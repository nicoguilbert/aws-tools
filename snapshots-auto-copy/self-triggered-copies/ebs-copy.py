################################################################
# This script copies every snapshot from us-west-2 to us-west-1
# Python 3.7
################################################################

import boto3
import time
import datetime
import re
from datetime import datetime, timedelta, timezone

import boto3

class Ec2Instances(object):
    
    def __init__(self, region_source, region_dest):
        self.region_source = region_source
        self.region_dest = region_dest
        self.aws_account = '728679744102'
        self.ec2_source = boto3.client('ec2', region_name=region_source)
        self.ec2_dest = boto3.client('ec2', region_name=region_dest)
        self.sns = boto3.resource('sns')
        self.snapshots = []

    def send_email(self, subject, message):
        print ("Sending email.")
        email_topic = self.sns.Topic('arn:aws:sns:us-west-1:728679744102:EmailsToSend')
        self.email_topic.publish(
                Subject = subject,
                Message = message
            )

    def get_nb_copy(self):
        response = self.ec2_dest.describe_snapshots(
            Filters=[{ 'Name': 'status', 'Values': ['pending', 'creating' ]} ],
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


    def set_snapshots_list(self):
        n = 0
        snapshots = self.get_snapshots()       
        
        for snapshot in snapshots:
            s = Snapshot(self.ec2_source, snapshot["SnapshotId"])
            already_copied = s.filter_snapshot()        
        
        if already_copied == False:
            self.snapshots.append(s)
            n = n + 1
        
        self.snapshot.sort(key=lambda r:r.start_time, reverse=True)
        print(str(n) + "EBS snapshots to copy from " + region_source)
        return n



    # deletion
    def get_autocopied_snapshots(self):
        snapshots = self.ec2.describe_snapshots(
            Filters=[{ 'Name': 'tag:SnapshotType', 'Values': 'AutomatedCopyCrossRegion' }],
            OwnerIds=[ 
                self.aws_account, 
            ],
        )
        return snapshots

    def delete_snapshot(self, snapshot_id):
        self.ec2.delete_snapshot(SnapshotId=snapshot_id)
    
    def delete_snapshots(self, older_days=14):
        delete_snapshots_num = 0
        snapshots = self.get_autocopied_snapshots()
        for snapshot in snapshots['Snapshots']:
            fmt_start_time = snapshot['StartTime']
            if (fmt_start_time < self.get_delete_data(older_days)):
                self.delete_snapshot(snapshot['SnapshotId'])
                delete_snapshots_num + 1
        return delete_snapshots_num

    def get_delete_data(self, older_days):
        delete_time = datetime.now(tz=timezone.utc) - timedelta(days=older_days)
        return delete_time;


class Snapshot(object):

    def __init__(self, ec2_client, snapshot_id):
        self.ec2 = ec2_client
        self.snapshot = ec2_client.Snapshot(snapshot_id) 
        self.id = self.snapshot.snapshot_id
        self.volume_id = self.snapshot.volume_id
        self.description = self.snapshot.description
        self.start_time = self.snapshot.start_time
        self.tags = self.snapshot.tags
        self.instance_name = ""
        self.


    def create_tag(self, key, value):
        print ("Creatin tag - " + key + ":" + value + ", snapshot_id: " + self.id)
        self.ec2.create_tags(
            Resources=[ self.id ], 
            Tags=[{'Key': key, 'Value':value},] 
        )
        self.tags.append({'Key': key, 'Value':value})

    def delete_tag(self, key, value):
        print ("Deleting tag - " + key + ":" + value + ", snapshot_id: " + self.id)
        self.ec2.delete_tags(
            Resources=[ self.id ], 
            Tags=[{'Key': key, 'Value':value},] 
        )
        self.tags = [t for t in self.tags if not (t['Key'] == key and t['Value'] == value)]

    def set_tags(self):
        if self.tags == []:
            self.create_tag("BackupCrossRegion", "Waiting")
        
        if (next((item for item in self.tags if item['Key'] == 'BackupCrossRegion'), False) == False):
                self.create_tag(CLIENT_SOURCE, snapshot_id, 'BackupCrossRegion', 'Waiting')
    
    def filter_snapshot(self):
        pattern = re.compile("^sc-")

        self.set_tags()
        
        for t in self.tags:
            # If the Name matches the pattern of copied snapshots
            if t['Key'] == 'Name':
                test_match = pattern.match(t['Value'])
                if test_match == None:
                    return True
            # If the snapshot has already been copied
            if t['Key'] == 'BackupCrossRegion' and t['Value'] == 'Done':
                return True

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

    def set_instance_name(instance_id):
        instance = ec2_source.Instance(instance_id)
        
        for tag in instance.tags:
            if tag["Key"] == "Name":
                self.instance_name = tag["Value"]

        self.instance_name = "NameUndefined"



            
def lambda_handler(event, context):
    print("event " + str(event))
    print("context " + str(context))
    ec2_reg = boto3.client('ec2')
    regions = ec2_reg.describe_regions()
    for region in regions['Regions']:
        region_name = region['RegionName']
        instances = Ec2Instances(region_name)
        deleted_counts = instances.delete_snapshots(1)
        print("deleted_counts for region "+ str(region_name) +" is " + str(deleted_counts))
    return 'completed'

######################
#  Global variables. #
######################

SOURCE_REGION = 'us-west-1'
DEST_REGION = 'us-west-2'

# How many days do you want to keep the snapshots
DAYS_OF_RETENTION = 14
RETENTION_TIME = DAYS_OF_RETENTION * 86400

EMAIL_SENDER = "nicolasguilbert.tours@gmail.com"
EMAIL_RECIPIENT = "nicolasguilbert.tours@gmail.com"
EMAIL_REGION = "us-west-2"

EC2_RESOURCE = boto3.resource('ec2')

######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
######################################################################################
# Original function (lot of typos like double quotes missing)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################

    







def get_snapshot_name(snapshot_id):
    snapshot = EC2_RESOURCE.Snapshot(snapshot_id)

    for tag in snapshot.tags:
        if tag["Key"] == "Name":
            return tag["Value"]

    return "NameUndefined"

###############################################
# Returns the description of the new snapshot.#
###############################################

def get_volume_description(snapshot_id):
    description = ""
    volume_id = get_volume_id(snapshot_id)
    
    if volume_id == "vol-ffffffff":
        description = "This snapshot was a copy of another.. "
    else: 
        # Puts a list in attachments. The list only contains one element
        # Or contains a string
        attachments = get_volume_attachments(volume_id)
        if attachments == False:
            description = "Volume did not exist. Could not find attachements."
        elif attachments == []:
            description = description + "Volume not attached/deleted." + " RegionSource: " + SOURCE_REGION
        else:
            # Puts a dictionnary containing the volume informations inside volume_dict
            volume_dict = attachments[0]
            instance_name = "Ec2Name: " + get_instance_name(volume_dict["InstanceId"])
            block_device = ", BlockDevice: " + volume_dict["Device"]
            description = description + instance_name + block_device + ", RegionSource: " + SOURCE_REGION

    return description


###############################################
# Will copy the snapshot to the other region. #
###############################################

def copy_snapshot(snapshot_id, tags):
    print ("Started copying.. snapshot_id: " + snapshot_id + ", from: " + SOURCE_REGION + ", to: " + DEST_REGION)
    description = get_volume_description(snapshot_id)

    try:
        copy_response = CLIENT_DEST.copy_snapshot(
            Description=description,
            SourceRegion=SOURCE_REGION,
            SourceSnapshotId=snapshot_id,
            DryRun=False
        )

    except:
        send_email(
                subject = "An EBS Snapshot not copied",
                message = """
                    {
                        "sender": "Sender Name  <%s>",
                        "recipient":"%s",
                        "aws_region":"%s",
                        "body": "The snapshot %s encountered  problem during the copy process. The copy did not succeed."
                    }
                """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION, snapshot_id)
        )
        

    new_snapshot_id = copy_response["SnapshotId"]
    print ('new_snapshot_id : ' + new_snapshot_id)
    old_snapshot = EC2_RESOURCE.Snapshot(snapshot_id)
    new_snapshot = EC2_RESOURCE.Snapshot(new_snapshot_id)
    
    #Copying tags from original snapshot to new snapshot
    try:
        tag = CLIENT_DEST.create_tags(
            Resources=[new_snapshot_id],
            Tags=tags
        )
    except:
        create_tag(CLIENT_DEST, new_snapshot_id, 'IssueWithTags', 'Colon')
        print ("This snapshot might contain tags starting by 'aws:'. No way to handle them now.")
        print (new_snapshot_id)
    
    
    name = get_snapshot_name(snapshot_id)
    # if here was tag "Name"
    if name != "NameUndefined":
        delete_tag(CLIENT_DEST, new_snapshot_id, 'Name', name)
    # if the value of the tag "Name" was empty
    if name == "":
        name = "NameEmpty"
    
    copy_name = "sc-" + name + "-" + old_snapshot.start_time.strftime("%Y-%m-%d")
    
    create_tag(CLIENT_DEST, new_snapshot_id, 'Name', copy_name)
    create_tag(CLIENT_DEST, new_snapshot_id, 'SnapshotType', 'AutomatedCopyCrossRegion')
    create_tag(CLIENT_DEST, new_snapshot_id, 'OriginalSnapshotID', snapshot_id)
    
    print("Successfully copyied.. snapshot_id: " + snapshot_id + ", from: " + SOURCE_REGION + ", to: " + DEST_REGION)
    
    delete_tag(CLIENT_SOURCE, snapshot_id, 'BackupCrossRegion', 'Waiting')
    create_tag(CLIENT_SOURCE, snapshot_id, 'BackupCrossRegion', 'Done')

    return new_snapshot_id

#################################################
# Will delete old snapshots on the other region #
#################################################

def delete_old_snapshots():
    response = CLIENT_DEST.describe_snapshots(
        Filters=[
            {
                'Name': 'status',
                'Values': [
                    'completed'
                ]
            },
            {
                'Name': 'tag:SnapshotType',
                'Values': [
                    'AutomatedCopyCrossRegion'
                ]
            }
        ],
        OwnerIds=[
            AWS_ACCOUNT,
        ],
    )
    
    snapshots = response["Snapshots"]
    resource = boto3.resource('ec2', region_name=DEST_REGION)
    for snapshot in snapshots:
        snapshot_id = snapshot["SnapshotId"]

        snap = resource.Snapshot(snapshot_id)
        delete_time = datetime.datetime.now() - datetime.timedelta(seconds=RETENTION_TIME)
        
        # These two lines are used to make sure we can compare both dates.
        start_time = snap.start_time.replace(tzinfo=None)
        delete_time = delete_time.replace(tzinfo=None)

        # If the snapshot is too old, we delete it. Godspeed, snapshot.
        try:
            if start_time < delete_time:
                print ("## => Deletion time")
                snap.delete()
                print ("## <= Deletion over")
        except:
            print ("This snapshot was probably 'InUse' by an Image. Won't be deleted.")


#################################
# Function called by AWS Lambda #
#################################

def lambda_handler(event, context):
    nb_copy = get_nb_copy(CLIENT_DEST)
    
    if nb_copy >= 5:
        print ("Already 5 snapshots being copied.")
        exit(0)
    
    copy_limit = 5 - nb_copy
    
    snapshots = get_snapshots(CLIENT_SOURCE)
    snapshot_list = get_snapshot_list(snapshots)
    
    if snapshot_list == []:
        events_client = boto3.client('events')
        response = events_client.disable_rule(
            Name="{0}-Trigger".format(context.function_name)
        )
        print ("Rule disabled. No more snapshots to copy")
        send_email(
                subject = "EBS Snapshot Copy finished",
                message = """
                    {
                        "sender": "Sender Name  <%s>",
                        "recipient":"%s",
                        "aws_region":"%s",
                        "body": "The copy process of EBS snapshots has just ended."
                    }
                """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION)
        )
        exit(0)
        
    i = 0

    for snapshort in snapshot_list:
        # 5 is the number of snapshot copies you can make at the same time on AWS
        if i < copy_limit:
            snapshot_id = snapshort[0]
            print ('copied snapshot id =' + snapshot_id)
            tags = snapshort[1]
            description = get_volume_description(snapshot_id)
            new_snapshot_id = copy_snapshot(snapshot_id, tags)
            i = i + 1
        else:
            break
    
    if i == 0:
        print ("No snapshots to copy at this call of the function")

    delete_old_snapshots()
