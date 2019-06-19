import json

frequency = "rate(10 minute)"

lambda_client = boto3.client('lambda')
events_client = boto3.client('events')

fn_name = "HelloWorld"
fn_role = 'arn:aws:iam::728679744102:role/rds_copy_snapshot_regions'
fn_arn = 'arn:aws:lambda:us-west-1:728679744102:function:HelloWorld'

def lambda_handler(event, context):
    ##########
    # Invoke #
    ##########

    
    name = "{0}-Trigger".format(fn_name)
    
    rule_response = events_client.put_rule(
        Name=name,
        ScheduleExpression=frequency,
        State='ENABLED',
    )   
    
    lambda_client.add_permission(
        FunctionName=fn_name,
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
                'Arn': fn_arn,
            },
        ]
    )n