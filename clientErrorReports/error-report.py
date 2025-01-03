import logging
import os, sys
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

# Add the parent directory to the Python path for Common Imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.serviceNow import create_service_now_incident, attach_file_to_ticket,create_service_now_request
from common.notifications import send_email

# Get the absolute path of the script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the absolute path of the configuration file
config_file_path = os.path.join(script_dir, "error-report-config.ini")

# Load the configuration file
config = configparser.ConfigParser()
config.read(config_file_path)

# Set up logging
log_file_path = os.path.join(script_dir, "error_report.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler()
    ]
)


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
smtp_from = f"{os.environ['COMPUTERNAME']}"
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
excluded_computer_names_path = os.path.join(script_dir, config.get("Excludeditems", "excluded_computer_names_path"))
excluded_user_codes_path = os.path.join(script_dir, config.get("Excludeditems", "excluded_user_codes_path"))

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


def send_file_to_ERA_with_curl(file_path):
    curl_command = [
        "curl", "-k", "-F", f"file=@{file_path}",
        f"https://{ERA_server}:8443/"
    ]

    try:
        logging.info("Sending Client Error Report to ERA using curl...")
        curl_response = subprocess.run(curl_command, capture_output=True, text=True)

        if curl_response.returncode == 0:
            logging.info("Curl response received.")
            response_text = curl_response.stdout
            #logging.info("Response Text:", response_text)

            # Extract the uid using regex
            uid_match = re.search(r'<div class="uid"[^>]*>([^<]+)</div>', response_text)
            if uid_match:
                uid = uid_match.group(1)
                #logging.info(f"Extracted UID: {uid}")
                era_url = f"https://{ERA_server}:8443/getResult/?uid={uid}"
                logging.info(era_url)
                return era_url
            else:
                logging.info("UID not found in the response.")
                return None
        else:
            logging.error(f"Failed to execute curl. Return code: {curl_response.returncode}")
            logging.error("Error Output:", curl_response.stderr)
            return None

    except Exception as e:
        logging.error(f"An error occurred while executing curl: {e}")
        return None


def main():
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
                logging.info(f"working on {source_path}")

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
                    external_unique_id = str(uuid.uuid4())
                    # Send zip to ERA if enabled
                    if use_ERA:
                        era_url = send_file_to_ERA_with_curl(destination_path)
                        if era_url:
                            body += f"\n\nERA Url= {era_url}"
                    # Check if the item should be excluded
                    if affected_user_id and affected_user_id.lower() in [code.lower() for code in excluded_user_codes] or \
                            computer_name.lower() in [name.lower() for name in excluded_computer_names]:
                        logging.info(
                            f"Skipping ServiceNow processing for excluded computer_name or user_code: {computer_name} - {affected_user_id}")
                        subject = f"Client Error Report for {computer_name} at {local_time_str} (Ticket Exclusion)"
                        send_email(smtp_recipients, subject, body, smtp_from,smtp_from_domain,smtp_server, smtp_port, meme_path=None)
                        continue
                    if ticket_type == 'incident':
                        # Create ServiceNow incident and get the incident number
                        ticket_number, sys_id = create_service_now_incident(
                            ticket_summary, ticket_description,
                            affected_user_id, configuration_item, external_unique_id,
                            urgency, impact, service_now_instance,service_now_table,service_now_api_user, service_now_api_password, assignment_group
                        )
                    elif ticket_type == 'request':
                        # Create ServiceNow incident and get the incident number
                        ticket_number, sys_id = create_service_now_request(
                            ticket_summary, ticket_description,
                            affected_user_id,service_now_instance,service_now_table,service_now_api_user, service_now_api_password, assignment_group,request_catalog_item,request_u_description
                        )
                        subject = f"Client Error Report for {computer_name} at {local_time_str} Ticket: {ticket_number}"
                    else:
                        logging.error('invalid ticket type')

                    # Attach the zip file to the ServiceNow incident
                    if ticket_number and sys_id:
                        zip_file_path = destination_path
                        attach_file_to_ticket(sys_id, zip_file_path,service_now_instance,service_now_attachment_table,service_now_api_user, service_now_api_password)
                        subject = f"Client Error Report for {computer_name} at {local_time_str} Ticket: {ticket_number}"

                    # send email
                    send_email(smtp_recipients, subject, body, smtp_from,smtp_from_domain,smtp_server, smtp_port, meme_path=None)

                    sleep(1)  # Introduce a delay of 1 second before working on next error report


if __name__ == '__main__':
    main()