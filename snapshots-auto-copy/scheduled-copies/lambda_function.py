import json
import time
import datetime
import boto3
import shared_variables
# Important to let these 'import' here so they take the possible new value of the global variables
import ebs_copy_script
import rds_copy_script

SOURCE_REGION = shared_variables.SOURCE_REGION
DEST_REGION = shared_variables.DEST_REGION
AWS_ACCOUNT = shared_variables.AWS_ACCOUNT

EMAIL_SENDER = shared_variables.EMAIL_SENDER
EMAIL_RECIPIENT = shared_variables.EMAIL_RECIPIENT
EMAIL_REGION = shared_variables.EMAIL_REGION

SNS = boto3.resource('sns')
EMAIL_TOPIC = shared_variables.EMAIL_TOPIC

RETENTION_TIME = shared_variables.RETENTION_TIME

CLIENT_SOURCE = boto3.client('ec2',region_name=SOURCE_REGION)
CLIENT_DEST = boto3.client('ec2', region_name=DEST_REGION)
EC2_RESOURCE = boto3.resource('ec2')
CLIENT_DB_SOURCE = boto3.client("rds", region_name=SOURCE_REGION)
CLIENT_DB_DEST = boto3.client("rds", region_name=DEST_REGION)

NOW = datetime.datetime.now()
# Please change that variable to the right time of launching
DAILY_LAUNCH_TIME = NOW.replace(hour=12, minute=0, second=0)
# The number of hours you won't get an email if the function is still calling itself
TIME_DELTA = datetime.timedelta(hours=1)

#CLIENT_LAMBDA = boto3.client("lambda", region_name=SOURCE_REGION)

def lambda_handler(event, context):
    #######
    # EBS #
    #######
    ebs_snapshots = ebs_copy_script.get_snapshots(CLIENT_SOURCE)
    ebs_snapshots_lists = ebs_copy_script.get_snapshot_list(ebs_snapshots)
    if ebs_snapshots_lists != []:
        ebs_nb_copy = ebs_copy_script.get_nb_copy(CLIENT_DEST)
        if ebs_nb_copy < 5:
            ebs_copy_script.main(ebs_snapshots_lists, ebs_nb_copy)
        else:
            print("More than 5 snapshots are already being copied right now.")
        
        # Email sent when something happens, change False with a condition
        if False:
            EMAIL_TOPIC.publish(
                Subject = "From SES: RDS Copy taking too long.",
                Message = """
                        {
                            "sender": "Sender Name  <%s>",
                            "recipient":"%s",
                            "aws_region":"%s",
                            "body": "There are still snapshots to copy at 5 PM."
                        }
                        """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION)
                )
    else:
        print("No EBS snapshot to copy.")

    #######
    # RDS #
    #######
    rds_snapshots_manual = rds_copy_script.get_snapshots(CLIENT_DB_SOURCE, "manual")
    rds_snapshots_automated = rds_copy_script.get_snapshots(CLIENT_DB_SOURCE, "automated")
    if rds_snapshots_automated != [] or rds_snapshots_manual != []:
        rds_nb_copy = rds_copy_script.get_nb_copy(CLIENT_DB_DEST)
        if rds_nb_copy < 5:
            rds_copy_script.main(rds_snapshots_manual, rds_snapshots_automated, rds_nb_copy)
        else:
            print("Already more than 5 RDS snapshots being copied.")
        
        if False:
            EMAIL_TOPIC.publish(
                Subject = "From SES: RDS Copy taking too long.",
                Message = """
                        {
                            "sender": "Sender Name  <%s>",
                            "recipient":"%s",
                            "aws_region":"%s",
                            "body": "There are still snapshots to copy at 5 PM."
                        }
                        """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION)
                )
    else:
        print("No RDS snapshot to copy.")
    
    ############
    # Deletion #
    ############
    
    ebs_copy_script.delete_old_snapshots()
    rds_copy_script.delete_old_snapshots()
