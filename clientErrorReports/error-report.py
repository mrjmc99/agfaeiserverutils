import logging
import os, sys
import shutil
import zipfile
from datetime import datetime
from time import sleep
import uuid
import re
import subprocess
from dotenv import load_dotenv

# Add the parent directory to the Python path for Common Imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.serviceNow import create_service_now_incident, attach_file_to_ticket,create_service_now_request
from common.notifications import send_email
from common.api import lookup_available_nodes
# Get the absolute path of the script
script_dir = os.path.dirname(os.path.abspath(__file__))

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


# Set env files to load
common_dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'common.env')
script_dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'error-report.env')

# Load env files
load_dotenv(common_dotenv_path)
load_dotenv(script_dotenv_path)


# -- AGFA / Error Report Variables --
EI_FQDN = os.getenv("EI_FQDN")
EI_USER = os.getenv("EI_USER")
EI_PASSWORD = os.getenv("EI_PASSWORD")
error_report_repo = os.getenv("ERROR_REPORT_REPO", "E:\\error-report-repo")
source_folder = os.getenv("SOURCE_FOLDER", "C:\\Agfa\\IMPAX_Agility\\error-report")
search_term = os.getenv("SEARCH_TERM", "comment")
ERA_server = os.getenv("ERA_SERVER", "")
use_ERA = os.getenv("USE_ERA", "false").lower() == "true"
excluded_computer_names_path = os.path.join(script_dir, os.getenv("EXCLUDED_COMPUTER_NAMES_PATH", "excluded_computer_names.txt"))
excluded_user_codes_path = os.path.join(script_dir, os.getenv("EXCLUDED_USER_CODES_PATH", "excluded_user_codes.txt"))

# -- Email Variables --
smtp_server = os.getenv("SMTP_SERVER", "")
smtp_port = int(os.getenv("SMTP_PORT", "25"))         # Convert to int
smtp_username = os.getenv("SMTP_USERNAME", "")
smtp_password = os.getenv("SMTP_PASSWORD", "None")
smtp_from_domain = os.getenv("SMTP_FROM_DOMAIN", "")
smtp_from = f"{os.environ['COMPUTERNAME']}"
# Parse comma-separated recipients into a list
smtp_recipients_string = os.getenv("SMTP_RECIPIENTS", "")
smtp_recipients = [r.strip() for r in smtp_recipients_string.split(",") if r.strip()]

# -- ServiceNow (Common) --
service_now_api_user = os.getenv("SN_API_USER", "")
service_now_api_password = os.getenv("SN_API_PASSWORD", "")
service_now_instance = os.getenv("SN_INSTANCE", "")
business_hours_start_time = os.getenv("SN_BUSINESS_HOURS_START_TIME", "08:00:00")
business_hours_end_time = os.getenv("SN_BUSINESS_HOURS_END_TIME", "17:00:00")

# -- ServiceNow (Error Report–Specific) --
service_now_table = os.getenv("SN_TABLE", "")
service_now_attachment_table = os.getenv("SN_ATTACHMENT_TABLE", "")
ticket_type = os.getenv("SN_TICKET_TYPE", "request")
configuration_item = os.getenv("SN_CONFIGURATION_ITEM", "")
request_u_description = os.getenv("SN_REQUEST_U_DESCRIPTION", "")
request_catalog_item = os.getenv("SN_REQUEST_CATALOG_ITEM", "")
assignment_group = os.getenv("SN_ASSIGNMENT_GROUP", "")
assignee = os.getenv("SN_ASSIGNEE", "")
after_hours_urgency = os.getenv("SN_AFTER_HOURS_URGENCY", "4")
after_hours_impact = os.getenv("SN_AFTER_HOURS_IMPACT", "4")
business_hours_urgency = os.getenv("SN_BUSINESS_HOURS_URGENCY", "3")
business_hours_impact = os.getenv("SN_BUSINESS_HOURS_IMPACT", "3")

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

                    # lookup cluster nodes and attach results to email
                    cluster_nodes = lookup_available_nodes(EI_FQDN, EI_USER, EI_PASSWORD)

                    # logging.info(f"Email Body: {message}")
                    if cluster_nodes:
                        body += f"\nEI Cluster: {EI_FQDN.upper()}"
                        body += f"\nCurrent Cluster Nodes: {cluster_nodes}"


                    # send email
                    send_email(smtp_recipients, subject, body, smtp_from,smtp_from_domain,smtp_server, smtp_port, meme_path=None)

                    sleep(1)  # Introduce a delay of 1 second before working on next error report


if __name__ == '__main__':
    main()