import json
import boto3

def lambda_handler(event, context):
    lambda_client = boto3.client('lambda')
    events_client = boto3.client('events')

    ebs_fn_name = "EbsSnapshotCopyCrossRegion"
    ebs_fn_arn = 'arn:aws:lambda:us-west-1:728679744102:function:EbsSnapshotCopyCrossRegion'
    
    frequency = "rate(5 minute)"
    name = "{0}-Trigger".format(ebs_fn_name)
    
    rule_response = events_client.put_rule(
        Name=name,
        ScheduleExpression=frequency,
        State='ENABLED',
    )   
    
    lambda_client.add_permission(
        FunctionName=ebs_fn_name,
        StatementId="{0}-Event".format(name),
        Action='lambda:InvokeFunction',
        Principal='events.amazonaws.com',
        SourceArn=rule_response['RuleArn'],
    )
    
    events_client.put_targets(
        Rule=name,
        Targets=[
            {
                'Id': "1",
                'Arn': ebs_fn_arn,
            },
        ]
    )
