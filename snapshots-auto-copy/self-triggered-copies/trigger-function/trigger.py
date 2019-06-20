import json
import boto3

def lambda_handler(event, context):
    lambda_client = boto3.client('lambda')
    events_client = boto3.client('events')

    ebs_fn_name = "EbsSnapshotCopyCrossRegion"
    ebs_fn_arn = 'arn:aws:lambda:us-west-1:728679744102:function:EbsSnapshotCopyCrossRegion'
    
    rds_fn_name = "RdsSnapshotCopyCrossRegion"
    rds_fn_arn = 'arn:aws:lambda:us-west-1:728679744102:function:RdsSnapshotCopyCrossRegion'
    
    frequency = "rate(1 minute)"
    ebs_name = "{0}-Trigger".format(ebs_fn_name)
    rds_name = "{0}-Trigger".format(rds_fn_name)

     
    # EBS
    try:
        rule_response = events_client.put_rule(
            Name=ebs_name,
            ScheduleExpression=frequency,
            State='ENABLED',
        )   
        print("Creating rule.")
        lambda_client.add_permission(
            FunctionName=ebs_fn_name,
            StatementId="{0}-Event".format(ebs_name),
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rule_response['RuleArn'],
        )
        events_client.put_targets(
            Rule=ebs_name,
            Targets=[
                {
                    'Id': "1",
                    'Arn': ebs_fn_arn,
                },
            ]
        )
    except:
        rule_response = events_client.enable_rule(
            Name=ebs_name
        )
        print("Rule already exists.")
    
    # RDS
    try:
        rule_response = events_client.put_rule(
            Name=rds_name,
            ScheduleExpression=frequency,
            State='ENABLED',
        )   
        print("Creating rule.")
        lambda_client.add_permission(
            FunctionName=rds_fn_name,
            StatementId="{0}-Event".format(rds_name),
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rule_response['RuleArn'],
        )
        events_client.put_targets(
            Rule=rds_name,
            Targets=[
                {
                    'Id': "1",
                    'Arn': rds_fn_arn,
                },
            ]
        )
    except:
        rule_response = events_client.enable_rule(
            Name=rds_name
        )
        print("Rule already exists.") 
        
    
