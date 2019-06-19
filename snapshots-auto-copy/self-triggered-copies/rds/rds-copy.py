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


######################################################################################
# Boto3 documentation.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
######################################################################################
# Original function (lot of typos like double quotes missing)
# https://timesofcloud.com/aws-lambda-copy-5-snapshots-between-region/
######################################################################################

######################
#  Global variables. #
######################

SOURCE_REGION = 'us-west-1'
DEST_REGION = 'us-west-2'
AWS_ACCOUNT = '728679744102'
SNS = boto3.resource('sns')
EMAIL_TOPIC = SNS.Topic('arn:aws:sns:us-west-1:728679744102:EmailsToSend')

NOW = datetime.datetime.now()
# Please change that variable to the right time of launching
DAILY_LAUNCH_TIME = NOW.replace(hour=12, minute=0, second=0)
# The number of hours you won't get an email if the function is still calling itself
TIME_DELTA = datetime.timedelta(hours=1)

# How many days do you want to keep the snapshots
DAYS_OF_RETENTION = 14
RETENTION_TIME = DAYS_OF_RETENTION * 86400

CLIENT_DB_SOURCE = boto3.client("rds", region_name=SOURCE_REGION)
CLIENT_DB_DEST = boto3.client("rds", region_name=DEST_REGION)
CLIENT_LAMBDA = boto3.client("lambda", region_name=SOURCE_REGION)

def get_snapshots(client, type):
    # DOES NOT WORK FOR AURORA ! ! !
    response = client.describe_db_snapshots(
            SnapshotType=type,
            IncludeShared=False,
            IncludePublic=False
    )
    
    #print ("response = ")
    #print (response)
    return response['DBSnapshots']

def get_nb_copy(client):
    response = client.describe_db_snapshots(
            #SnapshotType=type,
            IncludeShared=False,
            IncludePublic=False
    )
    snapshots = response['DBSnapshots']
    nb_copy = 0
    
    for snapshot in snapshots:
        if snapshot["Status"] == 'pending' or snapshot["Status"] == 'creating':
            nb_copy = nb_copy + 1
    return nb_copy
    
def launch_copy_snapshots(snapshots, type, copy_limit):    
    snapshot_list = []
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
        
        #########################################################
        # Original
        # copy_name = database + "-" + snapshot_name + "-" + snapshots[1].strftime("%Y-%m-%d")
        #########################################################
        # Why make the distinction between manual and automated?
        # Automated snapshot will have colons in their names
        # => TargetDBSnapshotIdentifier in the copy_db_snapshot
        # method won't accept that
        #########################################################
        
        if type == "automated":
            copy_name = "sc-" + database + "-" + start_time.strftime("%Y-%m-%d-%Hh%Mm")
        elif type == "manual":
            copy_name = "sc-" + snapshot_name + "-" + start_time.strftime("%Y-%m-%d-%Hh%Mm")
        
        print("Checking if " + copy_name + " is copied")

        try:
            CLIENT_DB_DEST.describe_db_snapshots(
                DBSnapshotIdentifier=copy_name
            )
            print("Already Copied")
            continue
        except:
            snapshot_list.append((database, snapshot_name, start_time))
            continue
            
    snapshot_list.sort(key=lambda r:r[2], reverse=True)
    
    print('list sorted=')
    print (snapshot_list)
    
    n = len(snapshot_list)
    print("length " + type)
    print (n)
    i = 0
    
    # info will contain informations about the number of snapshots being copied,
    # and the number of snapshot left to copy
    info = {}
    
    if snapshot_list == []:
        print("No " + type + "snapshots to copy.")
    else:
        for snap in snapshot_list:
            if type == "automated":
                copy_name = "sc-" + snap[0] + "-" + snap[2].strftime("%Y-%m-%d-%Hh%Mm")
            elif type == "manual":
                copy_name = "sc-" + snap[1] + "-" + snap[2].strftime("%Y-%m-%d-%Hh%Mm")
            
            response = CLIENT_DB_DEST.copy_db_snapshot(
                SourceDBSnapshotIdentifier='arn:aws:rds:' + SOURCE_REGION + ':' + AWS_ACCOUNT + ':snapshot:' + snap[1],
                TargetDBSnapshotIdentifier=copy_name,
                CopyTags=True
            )
                
            if response['DBSnapshot']['Status'] != "pending" and response['DBSnapshot']['Status'] != "available":
                raise Exception("Copy operation for " + copy_name + " failed!")
                print("Copied " + copy_name)
                # Send e-mail !!
                continue
        
            i = i + 1
            # if 5 snapshots are already being copied, it returns the number of snapshots left to copy. 
            if i == copy_limit:
                break
    
    info["SnapshotsBeingCopied"] = i
    info["SnapshotsRemaining"] = n - i
    return info
      
def delete_old_snapshots(snapshots, type):
    pattern = re.compile("^sc-")
    response = CLIENT_DB_DEST.describe_db_snapshots(
        #SnapshotType='manual'
        IncludeShared=False,
        IncludePublic=False,
    )

    if len(response['DBSnapshots']) == 0:
        raise Exception("No snapshots in second region found")
    
    snapshots_per_database = {}
    
    for snapshot in response['DBSnapshots']:
        if snapshot['Status'] != 'available':
            continue

        # Test if the snapshot name matches the pattern of automatically copied snapshots
        test_match = pattern.match(snapshot['DBSnapshotIdentifier'])
        #print(snapshot)
        #print(test_match)
        if test_match == None:
            continue
        
        delete_time = datetime.datetime.now() - datetime.timedelta(seconds=RETENTION_TIME)
        snapshot_start_time = snapshot['SnapshotCreateTime'].replace(tzinfo=None)
        delete_time = delete_time.replace(tzinfo=None)
        #print(snapshot_start_time)
        #print(delete_time)
        
        if snapshot_start_time < delete_time:
            print("Processing deletion of snapshot " + snapshot['DBSnapshotIdentifier'])
            CLIENT_DB_DEST.delete_db_snapshot(
                DBSnapshotIdentifier=snapshot['DBSnapshotIdentifier']
            )
            

def lambda_handler(event, context):
    global DAILY_LAUNCH_TIME
    if (NOW < DAILY_LAUNCH_TIME):
        DAILY_LAUNCH_TIME = DAILY_LAUNCH_TIME - datetime.timedelta(1)
        print("done")
    ####################Deletion########################
    snapshots_manual = get_snapshots(CLIENT_DB_SOURCE, "manual")
    delete_old_snapshots(snapshots_manual, "manual")
    snapshots_automated = get_snapshots(CLIENT_DB_SOURCE, "automated")
    delete_old_snapshots(snapshots_automated, "automated")
    ####################################################
    
    copy_limit = 5 - get_nb_copy(CLIENT_DB_DEST)

    if (copy_limit <= 0):
        # Invoke lambda again
        print("Already 5 snapshots being copied. Re-invoking function.")
        invoke_response = CLIENT_LAMBDA.invoke(
            FunctionName="SEStest",
            InvocationType='Event',
            #Payload=json.dumps(x)
        )
        exit(0)

    ####################Copy Manual#####################
    snapshots_manual = get_snapshots(CLIENT_DB_SOURCE, "manual")
    info = launch_copy_snapshots(snapshots_manual, "manual", copy_limit)
    ####################################################
    
    copy_limit = copy_limit - info["SnapshotsBeingCopied"] 
    print("copy")
    print(copy_limit)
    if (copy_limit <= 0):
        # Invoke lambda again
        print("Already 5 snapshots being copied. Re-invoking function.")
        invoke_response = CLIENT_LAMBDA.invoke(
            FunctionName="SEStest",
            InvocationType='Event',
            #Payload=json.dumps(x)
        )
        exit(0)

    ###################Copy Auto########################
    snapshots_automated = get_snapshots(CLIENT_DB_SOURCE, "automated")
    info = launch_copy_snapshots(snapshots_automated, "automated", copy_limit)
    ####################################################
    
    info["SnapshotsBeingCopied"] = 10
    info["SnapshotsRemaining"] = 1
    if (info["SnapshotsBeingCopied"] >= 5 and info["SnapshotsRemaining"] > 0):
        print("Already 5 snapshots being copied, and still snapshots to copy. Re-invoking the function.")
        #print(NOW)
        #print(DAILY_LAUNCH_TIME)
        
        #print(NOW - DAILY_LAUNCH_TIME)
        #print(NOW - DAILY_LAUNCH_TIME > TIME_DELTA)
        #print(DAILY_LAUNCH_TIME - NOW)
        # If it's been too long since the launch time..
        if (NOW - DAILY_LAUNCH_TIME > TIME_DELTA):
            print("Hello World")
            response = EMAIL_TOPIC.publish(
                Subject = "From SES: RDS Copy taking too long.",
                #MessageStructure = 'json',
                #Message = json.stringify(
                Message = """
                        {
                            "sender": "Sender Name <nicolasguilbert.tours@gmail.com>",
                            "recipient": "nicolasguilbert.tours@gmail.com",
                            "aws_region": "us-west-2",
                            "body": "Coucou"
                        }
                    """
            )
            print(response)
        '''
        invoke_response = CLIENT_LAMBDA.invoke(
            FunctionName="SEStest",
            InvocationType='Event',
        )
        '''
        exit(0)
    
    
'''
    my_ses.send_email(
        sender="Sender Name <nicolasguilbert.tours@gmail.com>",
        recipient="nicolasguilbert.tours@gmail.com",
        aws_region="us-west-2",
        subject="Snapshot copying taking a long time",
        body="""Hello ! 
            If you're reading this e-mail, it means that the 'RDS Snapshot CopyCrossRegion' function is still processing.
            The function was first called at """ + str(DAILY_LAUNCH_TIME) + """ and is still being called at """ + str(NOW) + """.
            There is still """ + str(info["SnapshotsRemaining"]) + """ snapshots to copy.
            Have a nice day.
            E-mail sent by Amazon SES.
            """
        )
    '''        
    #"The 'RDS Snapshot CopyCrossRegion' function is still processing. \n" 
                            #+ "The function was first called at " + str(DAILY_LAUNCH_TIME) + " and is still being called at " + str(NOW) + ".\n" 
                            #+ "There is still " + str(info["SnapshotsRemaining"]) + " snapshots to copy.\n" 
                            #+ "E-mail sent by Amazon SES."