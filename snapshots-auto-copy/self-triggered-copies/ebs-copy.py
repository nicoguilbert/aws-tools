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
    }
]

ACCOUNT = "728679744102"

# How many days do you want to keep the snapshots
DAYS_OF_RETENTION = 14

EMAIL_SENDER = "nicolasguilbert.tours@gmail.com"
EMAIL_RECIPIENT = "nicolasguilbert.tours@gmail.com"
EMAIL_REGION = "us-west-2"
TOPIC_ARN = "arn:aws:sns:us-west-1:728679744102:EmailsToSend"

class Ec2Instances(object):
    
    def __init__(self, region_source, region_dest):
        self.region_source = region_source
        self.region_dest = region_dest
        self.aws_account = ACCOUNT
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

        except Exception as e:
            print(e)
            '''
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
            '''
            print("The snapshot {0} encountered  problem during the copy process. The copy did not succeed.".format(old_snapshot.id))

    def copy_snapshots(self, copy_limit):
        n = 0
        self.set_snapshots()
        #print(str(self.snapshots))
        for s in self.snapshots:
            new_id = self.copy_snapshot(s)
            print("Snapshot " + str(s.id) + " successfully copied to snapshot " + str(new_id))
            n = n + 1
            if n == copy_limit:
                break
        return n
    
    # deletion
    def delete_snapshot(self, snapshot_id):
        try:
            self.ec2_dest.delete_snapshot(SnapshotId=snapshot_id)
        except:
            print("Error.")
            
    def get_autocopied_snapshots(self):
        snapshots = self.ec2_dest.describe_snapshots(
            Filters=[
                { 'Name': 'status', 'Values': [ 'completed' ] },
                { 'Name': 'tag:SnapshotType', 'Values': [ 'AutomatedCopyCrossRegion' ] }
            ],
            OwnerIds=[ 
                self.aws_account, 
            ],
        )
        return snapshots

    def get_delete_time(self, older_days):
        delete_time = datetime.now(tz=timezone.utc) - timedelta(days=older_days)
        return delete_time

    def delete_snapshots(self, older_days=14):
        delete_snapshots_num = 0

        snapshots = self.get_autocopied_snapshots()

        for snapshot in snapshots['Snapshots']:
            start_time = snapshot['StartTime']
            if (start_time < self.get_delete_time(older_days)):
                #try:
                self.delete_snapshot(snapshot['SnapshotId'])
                delete_snapshots_num = delete_snapshots_num + 1
                print("Snapshot " + snapshot['SnapshotId'] + " deleted")
                #except:
                #    print ("This snapshot was probably 'InUse' by an Image. Won't be deleted.")

        print(str(delete_snapshots_num) + " snapshots deleted on region " + self.region_dest)
        return delete_snapshots_num
        
        
####################################
####################################
####################################
####################################
####################################
####################################
####################################

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
                Resources=[str(self.id)],
                Tags=tags
            )
        return tag

    def copy_update_tags(self, old_snapshot):
        #Copying tags from original snapshot to new snapshot
        try:
            tag = self.copy_tags(old_snapshot.tags)
        except:
            self.create_tag('IssueWithTags', 'Colon')
            print ("This snapshot might contain tags starting by 'aws:'. No way to handle them now.")
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
    nb_copy_processing = 0
    i = 0
    ec2 = []

    for region in REGIONS:
        ec2.append(Ec2Instances(region["Source"], region["Destination"]))
        print(ec2[i].get_nb_copy())
        nb_copy_processing = nb_copy_processing + ec2[i].get_nb_copy()
        i = i + 1

    copy_limit = 5 - nb_copy_processing

    for n in range(0, i):
        if copy_limit <= 0:
            break

        nb_copied = ec2[n].copy_snapshots(copy_limit)
        print(str(nb_copied) + " snapshots copied")
        copy_limit = copy_limit - nb_copied
        ec2[n].delete_snapshots(14)



######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
######################################################################################
# Original function (lot of typos like double quotes missing)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################

#################################
# Function called by AWS Lambda #
#################################
'''

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

    '''
