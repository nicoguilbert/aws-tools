import json
import boto3

EMAIL_SENDER = "SysAdmin-AWS@doxcelerate.com"
EMAIL_RECIPIENT = "SysAdmin-AWS@doxcelerate.com"
EMAIL_REGION = "us-west-2"

SNS = boto3.resource('sns')
EMAIL_TOPIC = SNS.Topic('arn:aws:sns:us-west-1:728679744102:EmailsToSend')

def send_email(subject, message):
    print ("Sending email.")
    EMAIL_TOPIC.publish(
                Subject = subject,
                Message = message
            )
            
def lambda_handler(event, context):
    lambda_client = boto3.client('lambda')
    events_client = boto3.client('events')
    
    ebs_fn_name = "EbsSnapshotCopyCrossRegion"
    ebs_fn_arn = 'arn:aws:lambda:us-west-1:728679744102:function:EbsSnapshotCopyCrossRegion'
    
    rds_fn_name = "RdsSnapshotCopyCrossRegion"
    rds_fn_arn = 'arn:aws:lambda:us-west-1:728679744102:function:RdsSnapshotCopyCrossRegion'
    
    frequency = "rate(10 minutes)"
    ebs_rule_name = "{0}-Trigger".format(ebs_fn_name)
    rds_rule_name = "{0}-Trigger".format(rds_fn_name)

    # EBS
    ebs_rule_response = events_client.put_rule(
        Name=ebs_rule_name,
        ScheduleExpression=frequency, 
        State='ENABLED',
    )   
    print("Rule created or updated.")
    try:
        lambda_client.add_permission(
            FunctionName=ebs_fn_name,
            StatementId="{0}-Event".format(ebs_rule_name),
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=ebs_rule_response['RuleArn'],
        )
        print("add_permission() OK")
    except:
        pass
    try:
        events_client.put_targets(
            Rule=ebs_rule_name,
            Targets=[
                {
                    'Id': "1",
                    'Arn': ebs_fn_arn,
                },
            ]
        )
        print("Rule well targeted.")
        events_client.enable_rule(
            Name=ebs_rule_name
        )
    except:
        send_email(
                subject = "EBS Function CW Event still processing",
                message = """
                    {
                        "sender": "Sender Name  <%s>",
                        "recipient":"%s",
                        "aws_region":"%s",
                        "body": "EBS Function CW Event still processing"
                    }
                """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION)
        )
    
    # RDS
    rds_rule_response = events_client.put_rule(
            Name=rds_rule_name,
            ScheduleExpression=frequency,
            State='ENABLED',
        )   
    print("Rule created or updated.")
    try:
        lambda_client.add_permission(
            FunctionName=rds_fn_name,
            StatementId="{0}-Event".format(rds_rule_name),
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rds_rule_response['RuleArn'],
        )
        print("add_permission() OK")
    except:
        pass
    try:
        events_client.put_targets(
            Rule=rds_rule_name,
                Targets=[
                {
                    'Id': "2",
                    'Arn': rds_fn_arn,
                },
            ]
        )
        print("Rule well targeted.")
        rds_rule_response = events_client.enable_rule(
            Name=rds_rule_name
        )
    except:
        send_email(
                subject = "RDS Function CW Event still processing",
                message = """
                    {
                        "sender": "Sender Name  <%s>",
                        "recipient":"%s",
                        "aws_region":"%s",
                        "body": "RDS Function CW Event still processing"
                    }
                """ % (EMAIL_SENDER, EMAIL_RECIPIENT, EMAIL_REGION)
        )