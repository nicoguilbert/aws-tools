################################################################
# This script copies every snapshot from us-west-2 to us-west-1
# Python 3.7
################################################################

import boto3
import time
import datetime
import re
from datetime import datetime, timedelta, timezone


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


class Ec2Instances(object):
    
    def __init__(self, region_source, region_dest):
        self.region_source = region_source
        self.region_dest = region_dest
        self.aws_account = '728679744102'
        self.ec2_source = boto3.client('ec2', region_name=region_source)
        self.ec2_dest = boto3.client('ec2', region_name=region_dest)
        self.ec2_resource = boto3.resource('ec2')
        self.sns = boto3.resource('sns')
        self.snapshots = []

    def send_email(self, subject, message):
        print ("Sending email.")
        email_topic = self.sns.Topic('arn:aws:sns:us-west-1:728679744102:EmailsToSend')
        self.email_topic.publish(
                Subject = subject,
                Message = message
            )
    
    def sort(self):
        self.snapshots.sort(key=lambda r:r.start_time, reverse=True)

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

    def set_snapshots(self):
        n = 0
        snapshots = self.get_snapshots()       
        
        for snapshot in snapshots:
            s = EBSSnapshot(self.ec2_resource, snapshot["SnapshotId"])
            already_copied = s.filter_snapshot()        
        
            if already_copied == False:
                self.snapshots.append(s)
                n = n + 1
        
        self.sort()
        print(str(n) + "EBS snapshots to copy from " + self.region_source)
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

        except:
            self.send_email(
                subject = "An EBS Snapshot not copied",
                message = """
                    {
                        "sender": "Sender Name  <%s>",
                        "recipient":"%s",
                        "aws_region":"%s",
                        "body": "The snapshot %s encountered  problem during the copy process. The copy did not succeed."
                    }
                """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION, old_snapshot.id)
            )
            print("The snapshot {0} encountered  problem during the copy process. The copy did not succeed.".format(old_snapshot.id))
        


        new_s = EBSSnapshot(self.ec2_dest, copy_response["SnapshotId"])
        print ('new snapshot id : ' + new_s.id)
        
        new_s.copy_update_tags(old_snapshot)

        return new_s.id

    def copy_snapshots(self, copy_limit):
        n = 0
        self.set_snapshots()
        for s in self.snapshots:
            new_id = copy_snapshot(s)
            print("Snapshot " + s.id + " successfully copied to snapshot " + new_id)
            n = n + 1
            if n == copy_limit:
                exit(0)


class EBSSnapshot(object):

    def __init__(self, ec2_client, snapshot_id, region_source = None, region_dest = None):
        self.ec2 = ec2_client
        self.snapshot_client = ec2_client.Snapshot(snapshot_id) 
        self.id = self.snapshot_client.snapshot_id
        self.volume_id = self.snapshot_client.volume_id
        self.description = self.snapshot_client.description
        self.start_time = self.snapshot_client.start_time
        self.tags = self.snapshot_client.tags
        self.name = ""
        self.instance_name = ""
        if region_source != None:
            self.region_source = region_source
        if region_dest != None:
            self.region_dest = region_dest

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
    
    def copy_tags(self, tags):
        tag = self.ec2.create_tags(
                Resources=[self.id],
                Tags=tags
            )
        return tag

    def copy_update_tags(self, old_snapshot):
        #Copying tags from original snapshot to new snapshot
        try:
            tag = new_s.copy_tags(old_snapshot.tags)
        except:
            new_s.create_tag('IssueWithTags', 'Colon')
            print ("This snapshot might contain tags starting by 'aws:'. No way to handle them now.")
            print (new_s.id)
        
        # if there was a tag "Name"
        if old_snapshot.name != "NameUndefined":
            new_s.delete_tag('Name', name)
        # if the value of the tag "Name" was empty
        if old_snapshot.name == "":
            name = "NameEmpty"
    
        copy_name = "sc-" + name + "-" + old_snapshot.start_time.strftime("%Y-%m-%d")
    
        new_s.create_tag('Name', copy_name)
        new_s.create_tag('SnapshotType', 'AutomatedCopyCrossRegion')
        new_s.create_tag('OriginalSnapshotID', old_snapshot.id)
    
        print("Successfully copyied.. snapshot_id: " + old_snapshot.id + ", from: " + old_snapshot.region_source + ", to: " + old_snapshot.region_dest)
    
        old_snapshot.delete_tag('BackupCrossRegion', 'Waiting')
        old_snapshot.create_tag('BackupCrossRegion', 'Done')

        return new_snapshot_id

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

    def set_instance_name(self, instance_id):
        instance = ec2_source.Instance(instance_id)
        
        for tag in instance.tags:
            if tag["Key"] == "Name":
                self.instance_name = tag["Value"]

        self.instance_name = "NameUndefined"
        return self.instance_name

    def set_snapshot_name(self):
        for tag in self.tags:
            if tag["Key"] == "Name":
                self.name = tag["Value"]

        self.name = "NameUndefined"

    def set_new_snapshot_description(self):
        new_description = ""
    
        if self.volume_id == "vol-ffffffff":
            new_description = "This snapshot was a copy of another.. "
        else: 
            # Puts a list in attachments. The list only contains one element
            # Or contains a string
            attachments = get_volume_attachments(self.volume_id)
            if attachments == False:
                new_description = "Volume did not exist. Could not find attachements."
            elif attachments == []:
                new_description = new_description + "Volume not attached/deleted." + " RegionSource: " + region_source
            else:
                # Puts a dictionnary containing the volume informations inside volume_dict
                volume_dict = attachments[0]
                instance_name = "Ec2Name: " + set_instance_name(volume_dict["InstanceId"])
                block_device = ", BlockDevice: " + volume_dict["Device"]
                new_description = new_description + instance_name + block_device + ", RegionSource: " + region_source

        self.new_snapshot_description = new_description
    


            
def lambda_handler(event, context):
    #ec2_reg = boto3.client('ec2')
    #regions = ec2_reg.describe_regions()
    '''
    for region in regions['Regions']:
        region_name = region['RegionName']
        instances = Ec2Instances(region_name)
        deleted_counts = instances.delete_snapshots(1)
        print("deleted_counts for region "+ str(region_name) +" is " + str(deleted_counts))
    return 'completed'
    '''
    ec2 = Ec2Instances("us-west-1", "us-west-2")
    ec2.copy_snapshots(5)



######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
######################################################################################
# Original function (lot of typos like double quotes missing)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################



#################################################
# Will delete old snapshots on the other region #
#################################################
'''
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
        self.ec2_source.delete_snapshot(SnapshotId=snapshot_id)
    
    def delete_snapshots(self, older_days=14):
        delete_snapshots_num = 0
        snapshots = self.get_autocopied_snapshots()
        for snapshot in snapshots['Snapshots']:
            fmt_start_time = snapshot['StartTime']
            if (fmt_start_time < self.get_delete_data(older_days)):
                self.delete_snapshot(snapshot['SnapshotId'])
                delete_snapshots_num + 1
        return delete_snapshots_num

    def get_delete_time(self, older_days):
        delete_time = datetime.now(tz=timezone.utc) - timedelta(days=older_days)
        return delete_time;
    '''
