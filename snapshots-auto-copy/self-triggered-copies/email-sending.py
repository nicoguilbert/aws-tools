from __future__ import print_function
import json
import boto3
from botocore.exceptions import ClientError

print('Loading function')

def send_email(sender, recipient, aws_region, subject, body):
    # The character encoding for the email.
    CHARSET = "UTF-8"

    # Create a new SES resource and specify a region.
    client = boto3.client('ses',region_name=aws_region)

    try:
    #Provide the contents of the email.
        response = client.send_email(
            Destination={
                'ToAddresses': [
                    recipient,
                ],
            },
            Message={
                'Body': {
                    'Text': {
                        'Charset': CHARSET,
                        'Data': body,
                    },
                },
                'Subject': {
                    'Charset': CHARSET,
                    'Data': subject,
                },
            },
            Source=sender,
        # If you are not using a configuration set, comment or delete the
        # following line
            #ConfigurationSetName=CONFIGURATION_SET,
        )
# Display an error if something goes wrong.	
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])

def lambda_handler(event, context):
    #print("Received event: " + json.dumps(event, indent=2))
    
    message = event['Records'][0]['Sns']['Message']
    subject = event['Records'][0]['Sns']['Subject']
    message_dict = json.loads(message)
    
    sender = message_dict["sender"]
    recipient = message_dict["recipient"]
    aws_region = message_dict["aws_region"]
    body = message_dict["body"]
    
    #print("From SNS: " + str(message))
    #send_email("Sender Name <nicolasguilbert.tours@gmail.com>", "nicolasguilbert.tours@gmail.com", "us-west-2", "TestMan", message)

    send_email(sender, recipient, aws_region, subject, body)
    
    print ("SUCCESSFULY TRIGGERED ")
    #return message
