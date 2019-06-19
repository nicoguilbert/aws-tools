################################################################
# This script copies every snapshot from us-west-2 to us-west-1
# Python 2.7 only
################################################################

import boto3
import time
import datetime
import shared_variables

######################
#  Global variables. #
######################

SOURCE_REGION = shared_variables.SOURCE_REGION
DEST_REGION = shared_variables.DEST_REGION
AWS_ACCOUNT = shared_variables.AWS_ACCOUNT

EMAIL_TOPIC = shared_variables.EMAIL_TOPIC
EMAIL_SENDER = shared_variables.EMAIL_SENDER
EMAIL_RECIPIENT = shared_variables.EMAIL_RECIPIENT
EMAIL_REGION = shared_variables.EMAIL_REGION

RETENTION_TIME = shared_variables.RETENTION_TIME

CLIENT_SOURCE = boto3.client('ec2',region_name=SOURCE_REGION)
CLIENT_DEST = boto3.client('ec2', region_name=DEST_REGION)
EC2_RESOURCE = boto3.resource('ec2')

######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
######################################################################################
# Original function (lot of typos like double quotes missing)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################

# Returns the number of snapshots being copied at the moment
def get_nb_copy(client):
    response = client.describe_snapshots(
        Filters=[
            {
                'Name': 'status',
                'Values': [
                    'pending'
                ]
            }
        ],
        OwnerIds=[
            AWS_ACCOUNT,
        ],
    )
    return len(response["Snapshots"])

##############################################
# Gets all snapshots as per specified filter #
##############################################

def get_snapshots(client):
    response = client.describe_snapshots(
        Filters=[
            {
                'Name': 'status',
                'Values': [
                    'completed'
                ]
            }
        ],
        OwnerIds=[
            AWS_ACCOUNT,
        ],
    )
    return response["Snapshots"]

#Creating a list of snapshot_id and respective tags
def get_snapshot_list(snapshots):
    snapshot_list = []
    
    for snapshot in snapshots:  
        copyIsDone = False 
        snapshot_id = snapshot["SnapshotId"]
        resource = boto3.resource('ec2', region_name=SOURCE_REGION)
        snap = resource.Snapshot(snapshot_id)
        
        start_time = snap.start_time.replace(tzinfo=None)
        
        # if there's no tags    
        if ('Tags' not in snapshot.keys()):
            create_tag(CLIENT_SOURCE, snapshot_id, 'BackupCrossRegion', 'Waiting')
            tags = [{"Key":"BackupCrossRegion", "Value":"Waiting"}]
        # if there's no BackupCrossRegion tag
        else:
            if (next((item for item in snapshot['Tags'] if item['Key'] == 'BackupCrossRegion'), False) == False):
                create_tag(CLIENT_SOURCE, snapshot_id, 'BackupCrossRegion', 'Waiting')
            tags = snapshot["Tags"]
            
        for t in tags:
            if t['Key'] == 'BackupCrossRegion' and t['Value'] == 'Done':
                copyIsDone = True
        
        if copyIsDone == False:
            snapshot_list.append((snapshot_id, tags, start_time))
    
    # snapshot_list <=> [ (id, [tags], start_time), (id,...), ...]
    # Next line sorts the list by creation time
    snapshot_list.sort(key=lambda r:r[2], reverse=True)
    
    return snapshot_list

##########################################################
# The next 4 functions are used to get informations about 
# the EC2 instance and the EBS volume, if they do exist.
##########################################################

# Returns the ID of the volume related to the snapshot
def get_volume_id(snapshot_id):
    snapshot = EC2_RESOURCE.Snapshot(snapshot_id)    
    return snapshot.volume_id

################################################################
# Returns a list of information (python dictionnaries) about the 
# volume attachments :
# AttachTime (datetime), Device (string - name of the device)
# InstanceId (string), State (string),
# VolumeId (string), DeleteOnTermination (boolean)
################################################################

def get_volume_attachments(volume_id):
    volume_exists = True
    try:
        response = CLIENT_SOURCE.describe_volumes(
            VolumeIds=[
                volume_id,
            ],
        )
    except:
        print ("The volume '" + volume_id + "' cannot be found. Must have been deleted")
        volume_exists = False
    
    if volume_exists == True:
        volume = EC2_RESOURCE.Volume(volume_id)
        return volume.attachments
    else:
        return False

def get_instance_name(instance_id):
    instance = EC2_RESOURCE.Instance(instance_id)
        
    for tag in instance.tags:
        #print tag
        if tag["Key"] == "Name":
            return tag["Value"]

    return "NameUndefined"

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


####################################################
# Simple functions helping creating/deletinig tags #
####################################################

def delete_tag(client, snapshot_id, key, value):
    print ("Deleting tag - " + key + ":" + value + ", snapshot_id: " + snapshot_id)
    client.delete_tags(
        Resources=[snapshot_id],
        Tags=[
            {
                'Key': key,
                'Value':value
            },
        ]
    )

def create_tag(client, snapshot_id, key, value):
    print ("Creating tag - " + key + ":" + value + ", snapshot_id: " + snapshot_id)
    client.create_tags(
        Resources=[snapshot_id],
        Tags=[
            {
                'Key': key,
                'Value':value 
            },
        ]
    )

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
        message = "ERROR: The snapshot " + snapshot_id + " couldn't be copied."
        EMAIL_TOPIC.publish(
                Subject = "From SES: EBS snapshot not copied.",
                Message = """
                        {
                            "sender": "Sender Name  <%s>",
                            "recipient":"%s",
                            "aws_region":"%s",
                            "body": "%s
                        }
                        """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION, message)
                )
        print("ERROR: The snapshot " + snapshot_id + " couldn't be copied.")

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
    
    #create_tag(CLIENT_SOURCE, snapshot_id, 'CopyCrossRegionID', new_snapshot_id)
    print ("Successfully copyied.. snapshot_id: " + snapshot_id + ", from: " + SOURCE_REGION + ", to: " + DEST_REGION)
    
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
        
        print (snapshot_id)
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

def main(snapshot_list, nb_copy):
    i = 0
    copy_limit = 5 - nb_copy
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

