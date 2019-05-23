# This script copies every snapshot from us-west-2 to us-west-1
# Python 2.7 only

import boto3
import time
import datetime


# Boto3 documentation
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
# Original function (lot of typos like double quotes missing)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/

region_source = 'us-west-2'
region_dest = 'us-west-1'
aws_account_id = '113186746640'
# How many days do you want to keep the snapshots
days_of_retention = 1 
retention_time = days_of_retention * 86400

client_source = boto3.client('ec2',region_name=region_source)
client_dest = boto3.client('ec2', region_name=region_dest)
ec2_resource = boto3.resource('ec2')

#Getting all snapshots as per specified filter
def get_snapshots():
    response = client_source.describe_snapshots(
        Filters=[
            {
                'Name': 'status',
                'Values': [
                    'completed'
                ]
            }
        ],
        OwnerIds=[
            aws_account_id,
        ],
    )
    #print response["Snapshots"]
    return response["Snapshots"]

#Creating a list of snapshot_id and respective tags
def get_snapshot_list(snapshots):
    snapshot_list = []
    
    for snapshot in snapshots:  
        copyIsDone = False 
        snapshot_id = snapshot["SnapshotId"]
        tags = snapshot["Tags"]
        
        snap = ec2_resource.Snapshot(snapshot_id)
        delete_time = datetime.datetime.now() - datetime.timedelta(seconds=retention_time)

        # These two lines are used to make sure we can compare both dates.
        start_time = snap.start_time.replace(tzinfo=None)
        delete_time = delete_time.replace(tzinfo=None)

        # If the snapshot is too old, we delete it. Godspeed, snapshot.
        if start_time < delete_time:
            snap.delete()
        
        else: 
            for t in tags:
                if t["Key"] == "BackupCrossRegion" and t["Value"] == "Done":
                    copyIsDone = True
        
            if copyIsDone == False:
                snapshot_list.append((snapshot_id, tags))
    
    #print snapshot_list
    return snapshot_list

# Returns the ID of the volume related to the snapshot
def get_volume_id(snapshot_id):
    snapshot = ec2_resource.Snapshot(snapshot_id)    
    # print "The snapshot about to be copied is related to volume : " + snapshot.volume_id
    return snapshot.volume_id

# Returns a list of information (dictionnaries) about the volume attachments :
# AttachTime (datetime), Device (string - name of the device)
# InstanceId (string), State (string),
# VolumeId (string), DeleteOnTermination (boolean)
def get_volume_attachments(volume_id):
    volume = ec2_resource.Volume(volume_id)
    return volume.attachments

def get_instance_name(instance_id):
    instance = ec2_resource.Instance(instance_id)
    tags = instance.tags[0]
    # Change that to make sure it returns the name?
    return tags["Value"]

def get_volume_description(snapshot_id):
    description = ""
    volume_id = get_volume_id(snapshot_id)
    if volume_id == "vol-ffffffff":
        description = "This snapshot was a copy of another.. "
    else:
        # Puts a list in list_attachments. The list only contains one element
        list_attachments = get_volume_attachments(volume_id)

        if list_attachments == []:
            description = description + "Not attached. " + " RegionSource: " + region_source
        else:
            # Puts a dictionnary containing the volume informations inside volume_dict
            volume_dict = list_attachments[0]
            instance_name = "Ec2Name: " + get_instance_name(volume_dict["InstanceId"])
            block_device = ", BlockDevice: " + volume_dict["Device"]
            description = description + instance_name + block_device + ", RegionSource: " + region_source

    return description

#Copying snapshot with tags
def copy_snapshot(snapshot_id, tags):
    print "Started copying.. snapshot_id: " + snapshot_id + ", from: " + region_source + ", to: " + region_dest
    
    try:
        copy_response = client_dest.copy_snapshot(
            Description=get_volume_description(snapshot_id),
            SourceRegion=region_source,
            SourceSnapshotId=snapshot_id,
            DryRun=False
        )
    except Exception, e:
        raise e

    new_snapshot_id = copy_response["SnapshotId"]
    print 'new_snapshot_id : ' + new_snapshot_id
    new_snapshot = ec2_resource.Snapshot(new_snapshot_id)
    
    #Copying tags from original snapshot in new snapshot
    tag = client_dest.create_tags(
        Resources=[new_snapshot_id],
        Tags=tags
    )
    
    create_tag(client_dest, new_snapshot_id, 'OriginalSnapshotID', snapshot_id)
    #delete_tag(client_source, snapshot_id, 'Backup', 'Yes')
    create_tag(client_source, snapshot_id, 'BackupCrossRegion', 'Done')
    create_tag(client_source, snapshot_id, 'CopyCrossRegionID', new_snapshot_id)
    print "Successfully copyied.. snapshot_id: " + snapshot_id + ", from: " + region_source + ", to: " + region_dest
    return new_snapshot_id
    
def delete_tag(client, snapshot_id, key, value):
    print "Deleting tag - " + key + ":" + value + ", snapshot_id: " + snapshot_id
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
    print "Creating tag - " + key + ":" + value + ", snapshot_id: " + snapshot_id
    client.create_tags(
        Resources=[snapshot_id],
        Tags=[
            {
                'Key': key,
                'Value':value 
            },
        ]
    )

def lambda_handler(event, context):
    snapshots = get_snapshots()
    snapshot_list = get_snapshot_list(snapshots)

    # main function
    i = 0

    for snapshort in snapshot_list:
        # 5 is the number of snapshot copies you can make at the same time on AWS
        print i
        if i < 5:
            snapshot_id = snapshort[0]
            print 'copied snapshot id =' + snapshot_id 
            tags = snapshort[1]
            print snapshort[1]
            new_snapshot_id = copy_snapshot(snapshot_id, tags)
            i = i + 1
        else:
            exit(0)
