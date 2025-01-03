import os
import shutil
import zipfile
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from time import sleep
import requests
import uuid
import configparser
import re
import subprocess

# Get the absolute path of the script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the absolute path of the configuration file
config_file_path = os.path.join(script_dir, "error-report-config.ini")

# Load the configuration file
config = configparser.ConfigParser()
config.read(config_file_path)

# agfa variables
error_report_repo = config.get("Agfa", "error_report_repo")
source_folder = config.get("Agfa", "source_folder")
search_term = config.get("Agfa", "search_term")
ERA_server = config.get("Agfa", "ERA_server")
use_ERA = config.get("Agfa", "use_ERA").lower() == "true"


# email variables
smtp_server = config.get("Email", "smtp_server")
smtp_port = int(config.get("Email", "smtp_port"))
smtp_username = config.get("Email", "smtp_username")
smtp_password = config.get("Email", "smtp_password")
smtp_from_domain = config.get("Email", "smtp_from_domain")
smtp_from = f"{os.environ['COMPUTERNAME']}@{smtp_from_domain}"
smtp_recipients_string = config.get("Email", "smtp_recipients")
smtp_recipients = smtp_recipients_string.split(",")

# service now variables
service_now_instance = config.get("ServiceNow", "instance")
service_now_table = config.get("ServiceNow", "table")
service_now_attachment_table = config.get("ServiceNow", "attachment_table")
service_now_api_user = config.get("ServiceNow", "api_user")
service_now_api_password = config.get("ServiceNow", "api_password")
ticket_type = config.get("ServiceNow", "ticket_type")
configuration_item = config.get("ServiceNow", "configuration_item")
assignment_group = config.get("ServiceNow", "assignment_group")
assignee = config.get("ServiceNow", "assignee")
request_u_description = config.get("ServiceNow", "request_u_description")
request_catalog_item = config.get("ServiceNow", "request_catalog_item")
business_hours_start_time = config.get("ServiceNow", "business_hours_start_time")
business_hours_end_time = config.get("ServiceNow", "business_hours_end_time")
after_hours_urgency = config.get("ServiceNow", "after_hours_urgency")
after_hours_impact = config.get("ServiceNow", "after_hours_impact")
business_hours_urgency = config.get("ServiceNow", "business_hours_urgency")
business_hours_impact = config.get("ServiceNow", "business_hours_impact")

# excluded items variables
excluded_computer_names_path = config.get("Excludeditems", "excluded_computer_names_path")
excluded_user_codes_path = config.get("Excludeditems", "excluded_user_codes_path")

# Ensure excluded items files exist, create them if they don't
if not os.path.exists(excluded_computer_names_path):
    open(excluded_computer_names_path, 'w').close()

if not os.path.exists(excluded_user_codes_path):
    open(excluded_user_codes_path, 'w').close()

# Get the current time and day of the week
current_time = datetime.now().time()
current_day = datetime.now().weekday()

# Define business hours
business_hours_start = datetime.strptime(business_hours_start_time, "%H:%M:%S").time()
business_hours_end = datetime.strptime(business_hours_end_time, "%H:%M:%S").time()

# Set default values
urgency = after_hours_urgency  # Default value for after hours and weekends
impact = after_hours_urgency  # Default value for after hours and weekends

# Check if it's business hours
if business_hours_start <= current_time <= business_hours_end and current_day < 5:  # Monday to Friday
    urgency = business_hours_urgency
    impact = business_hours_impact


def read_excluded_values(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file.readlines()]


# Load excluded values from text files
excluded_computer_names = read_excluded_values(excluded_computer_names_path)
excluded_user_codes = read_excluded_values(excluded_user_codes_path)


def send_email(smtp_recipients, subject, body):
    msg = MIMEText(body)
    msg["From"] = smtp_from
    msg["To"] = ", ".join(smtp_recipients)  # Join smtp_recipients with a comma and space
    msg["Subject"] = subject

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.sendmail(smtp_from, smtp_recipients, msg.as_string())
        server.quit()
        print(f"Email sent to {', '.join(smtp_recipients)}")
    except Exception as e:
        print(f"Email sending failed to {', '.join(smtp_recipients)}: {e}")


def create_service_now_incident(summary, description, affected_user_id, configuration_item, external_unique_id, urgency,
                                impact, device_name, ticket_type):
    service_now_api_url = f"https://{service_now_instance}/api/now/table/{service_now_table}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "u_short_description": summary,
        "u_description": description,
        "u_affected_user_id": affected_user_id,
        "u_configuration_item": configuration_item,
        "u_external_unique_id": external_unique_id,
        "u_urgency": urgency,
        "u_impact": impact,
        "u_type": ticket_type,
        "u_assignment_group": assignment_group,
    }

    try:
        print("Ticket Creation Payload:", payload)  # Print payload for debugging
        response = requests.post(
            service_now_api_url,
            headers=headers,
            auth=(service_now_api_user, service_now_api_password),
            json=payload,
        )

        print("Ticket Creation Response Status Code:", response.status_code)  # Print status code for debugging
        print("Ticket Creation Response Content:", response.text)  # Print response content for debugging

        if response.status_code == 201:
            incident_number = response.json().get("result", {}).get("u_task_string")
            sys_id = response.json().get('result', {}).get('u_task', {}).get('value')
            print(f"ServiceNow incident created successfully: {incident_number} {sys_id}")
            return incident_number, sys_id
        else:
            print(f"Failed to create ServiceNow incident. Response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while creating ServiceNow incident: {e}")

    return None, None


def create_service_now_request(summary, description, affected_user_id, ):
    service_now_api_url = f"https://{service_now_instance}/api/now/table/{service_now_table}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "u_type": 'request',
        "u_requested_by_user_id": affected_user_id,
        "u_affected_user_id": affected_user_id,
        #"u_phone": '123-456-7890',
        #"u_email": 'pacstest@adventhealth.com',
        "u_catalog_item": request_catalog_item,
        "u_description": request_u_description,
        #"u_variables": f"short_description::{summary}::description::{description}::phone::123-456-7890::fax::::affected_user"
        #               f"::{affected_user_id}::email::::requester::{affected_user_id}::requester_location"
        #               f"::f4fc4d43dbc3a200ec73f81ebf961972::affected_user_location::f4fc4d43dbc3a200ec73f81ebf961972"
        "u_variables": f"assignment_group::{assignment_group}::priority::3::assignee"
                       f"::::short_description::{summary}"
                       f"::description::{description}"
                       f"::requester::::affected_user::::email::"
                       f"::phone::::requester_location::::affected_user_location::::"
    }

    try:
        print("Ticket Creation Payload:", payload)  # Print payload for debugging
        response = requests.post(
            service_now_api_url,
            headers=headers,
            auth=(service_now_api_user, service_now_api_password),
            json=payload,
        )

        print("Ticket Creation Response Status Code:", response.status_code)  # Print status code for debugging
        print("Ticket Creation Response Content:", response.text)  # Print response content for debugging

        if response.status_code == 201:
            ticket_number = response.json().get("result", {}).get("u_task_string")
            sys_id = response.json().get('result', {}).get('u_task', {}).get('value')
            print(f"ServiceNow Request created successfully: {ticket_number} {sys_id}")
            return ticket_number, sys_id
        else:
            print(f"Failed to create ServiceNow incident. Response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while creating ServiceNow incident: {e}")

    return None, None


def attach_file_to_ticket(sys_id, file_path):
    attachment_api_url = f"https://{service_now_instance}/api/now/attachment/upload"

    headers = {
        "Accept": "application/json",
    }

    data = {
        "Content-Type": "application/octet-stream",
        "table_name": service_now_attachment_table,
        "table_sys_id": sys_id,
        "filename": os.path.basename(file_path),
    }

    files = {
        'file': (os.path.basename(file_path), open(file_path, 'rb')),
    }

    try:
        print("Sending attachment request...")
        print("Headers:", headers)
        print("Data:", data)
        print("Files:", files)
        attachment_response = requests.post(
            attachment_api_url,
            headers=headers,
            auth=(service_now_api_user, service_now_api_password),
            data=data,
            files=files,
        )

        print("Attachment response status code:", attachment_response.status_code)
        print("Attachment response text:", attachment_response.text)

        if attachment_response.status_code == 201:
            print("File attached to ServiceNow Ticket successfully")
        else:
            print(f"Failed to attach file to ServiceNow Ticket. Response: {attachment_response.text}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while attaching the file to ServiceNow Ticket: {e}")


def send_file_to_ERA_with_curl(file_path):
    curl_command = [
        "curl", "-k", "-F", f"file=@{file_path}",
        f"https://{ERA_server}:8443/"
    ]

    try:
        print("Sending Client Error Report to ERA using curl...")
        curl_response = subprocess.run(curl_command, capture_output=True, text=True)

        if curl_response.returncode == 0:
            print("Curl response received.")
            response_text = curl_response.stdout
            #print("Response Text:", response_text)

            # Extract the uid using regex
            uid_match = re.search(r'<div class="uid"[^>]*>([^<]+)</div>', response_text)
            if uid_match:
                uid = uid_match.group(1)
                #print(f"Extracted UID: {uid}")
                era_url = f"https://{ERA_server}:8443/getResult/?uid={uid}"
                print(era_url)
                return era_url
            else:
                print("UID not found in the response.")
                return None
        else:
            print(f"Failed to execute curl. Return code: {curl_response.returncode}")
            print("Error Output:", curl_response.stderr)
            return None

    except Exception as e:
        print(f"An error occurred while executing curl: {e}")
        return None



def send_file_to_ERA(file_path):
    def send_file_to_ERA(file_path):
        ERA_api_url = f"https://{ERA_server}:8443/"
        print(ERA_api_url)

        files = {
            'file': (os.path.basename(file_path), open(file_path, 'rb'), "application/x-zip-compressed"),
        }

        try:
            print("Sending Client Error Report to ERA request...")
            ERA_response = requests.post(
                ERA_api_url,
                files=files,
                verify=False
            )

            print("ERA Processing response status code:", ERA_response.status_code)
            print("ERA Processing response text:", ERA_response.text)

            if ERA_response.status_code == 200:
                print("ERA Processing successful")
            else:
                print(f"Failed to complete ERA Processing. Response: {ERA_response.text}")

        except requests.exceptions.RequestException as e:
            print(f"An error occurred while Processing ERA: {e}")
        finally:
            files['file'][1].close()  # Make sure to close the file after the request



if not os.path.exists(error_report_repo):
    os.makedirs(error_report_repo)

for root, _, files in os.walk(source_folder):
    for file in files:
        if search_term in file:
            source_path = os.path.join(root, file)
            relative_path = os.path.relpath(source_path, source_folder)
            destination_path = os.path.join(error_report_repo, relative_path)

            destination_directory = os.path.dirname(destination_path)
            os.makedirs(destination_directory, exist_ok=True)
            if os.path.exists(destination_path):
                continue

            original_timestamp = os.path.getmtime(source_path)  # Get the original file's timestamp
            shutil.copy2(source_path, destination_path)  # Use shutil.copy2() to preserve timestamps
            print(f"working on {source_path}")

            with zipfile.ZipFile(destination_path, "r") as zip_ref:
                user_code = None
                comment_content = None
                for entry in zip_ref.namelist():
                    if "comment.txt" in entry:
                        with zip_ref.open(entry) as comment_file:
                            comment_content = comment_file.read().decode("utf-8")
                            break

                    if entry.startswith("logs/") and "agility" in entry:
                        with zip_ref.open(entry) as log_file:
                            for line in log_file:
                                line = line.decode("utf-8")
                                if "userCode=" in line:
                                    user_code = line.split("userCode=")[1].split("@")[0]
                                    break

                computer_name = os.path.dirname(relative_path).lstrip("\\")
                local_time = datetime.fromtimestamp(original_timestamp)
                local_time_str = local_time.strftime('%Y-%m-%d %H:%M:%S')
                subject = f"Client Error Report for {computer_name} at {local_time_str} (Ticket Creation Failure)"
                body = f"EI Error Report Comment:\n{comment_content}\nUserID: {user_code}\nWorkstation: {computer_name}"
                ticket_summary = f"Client Error Report for {computer_name} at {local_time_str}"
                ticket_description = body
                affected_user_id = user_code
                device_name = computer_name
                external_unique_id = str(uuid.uuid4())
                # Send zip to ERA if enabled
                if use_ERA:
                    era_url = send_file_to_ERA_with_curl(destination_path)
                    if era_url:
                        body += f"\n\nERA Url= {era_url}"
                # Check if the item should be excluded
                if affected_user_id and affected_user_id.lower() in [code.lower() for code in excluded_user_codes] or \
                        computer_name.lower() in [name.lower() for name in excluded_computer_names]:
                    print(
                        f"Skipping ServiceNow processing for excluded computer_name or user_code: {computer_name} - {affected_user_id}")
                    subject = f"Client Error Report for {computer_name} at {local_time_str} (Ticket Exclusion)"
                    send_email(smtp_recipients, subject, body)
                    continue
                if ticket_type == 'incident':
                    # Create ServiceNow incident and get the incident number
                    ticket_number, sys_id = create_service_now_incident(
                        ticket_summary, ticket_description,
                        affected_user_id, configuration_item, external_unique_id,
                        urgency, impact, device_name, ticket_type
                    )
                elif ticket_type == 'request':
                    # Create ServiceNow incident and get the incident number
                    ticket_number, sys_id = create_service_now_request(
                        ticket_summary, ticket_description,
                        affected_user_id
                    )
                    subject = f"Client Error Report for {computer_name} at {local_time_str} Ticket: {ticket_number}"
                else:
                    print('invalid ticket type')

                # Attach the zip file to the ServiceNow incident
                if ticket_number and sys_id:
                    zip_file_path = destination_path
                    attach_file_to_ticket(sys_id, zip_file_path)
                    subject = f"Client Error Report for {computer_name} at {local_time_str} Ticket: {ticket_number}"



                # send email
                send_email(smtp_recipients, subject, body)

                sleep(1)  # Introduce a delay of 1 second before working on next error report
