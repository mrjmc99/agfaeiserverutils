import mmap
import sys, os
import re
import shutil
import logging
import requests
import socket
import uuid
from requests.exceptions import Timeout
from datetime import datetime, timedelta
from dotenv import load_dotenv
# Add the parent directory to the Python path for Common Imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.api import get_token,release_token,lookup_available_nodes
from common.serviceNow import create_service_now_incident, attach_file_to_ticket
from common.notifications import send_email


# Optimize logging by limiting verbosity to important messages
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Compile regex patterns once at the start
event_pattern = re.compile(r".*?(JBoss EAP.*?(started|stopped)|Timeout reached after 60s\. Calling halt)")

# Get the absolute path of the script
script_dir = os.path.dirname(os.path.abspath(__file__))


# Set env files to load
common_dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'common.env')
script_dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'jboss-check.env')

# Load env files
load_dotenv(common_dotenv_path)
load_dotenv(script_dotenv_path)

# -- AGFA / Jboss Check Variables --
EI_FQDN = os.getenv("EI_FQDN")
EI_USER = os.getenv("EI_USER")
EI_PASSWORD = os.getenv("EI_PASSWORD")
log_dir = os.getenv("LOG_DIR")
EI_jboss_path = os.getenv("EI_JBOSS_PATH")
crashdump_logs_folder = os.getenv("CRASHDUMP_LOGS_FOLDER")
# Construct the absolute path of the last_processed_event_file
last_processed_event_file = os.path.join(os.path.dirname(__file__), os.getenv("LAST_PROCESSED_EVENT_FILE"))
TOKEN = None

# Email variables
smtp_server = os.getenv("SMTP_SERVER")
smtp_port = int(os.getenv("SMTP_PORT", 25))  # Default to port 25 if not specified
smtp_username = os.getenv("SMTP_USERNAME")
smtp_password = os.getenv("SMTP_PASSWORD")
smtp_from_domain = os.getenv("SMTP_FROM_DOMAIN")
smtp_from = f"{os.environ['COMPUTERNAME']}"
smtp_recipients = os.getenv("SMTP_RECIPIENTS", "").split(",")

# ServiceNow variables
service_now_instance = os.getenv("SN_INSTANCE")
service_now_table = os.getenv("SN_TABLE")
service_now_attachment_table = os.getenv("SN_ATTACHMENT_TABLE")
service_now_api_user = os.getenv("SN_API_USER")
service_now_api_password = os.getenv("SN_API_PASSWORD")
ticket_type = os.getenv("SN_TICKET_TYPE")
configuration_item = os.getenv("SN_CONFIGURATION_ITEM")
assignment_group = os.getenv("SN_ASSIGNMENT_GROUP")
assignee = os.getenv("SN_ASSIGNEE")
business_hours_start_time = os.getenv("SN_BUSINESS_HOURS_START_TIME")
business_hours_end_time = os.getenv("SN_BUSINESS_HOURS_END_TIME")
after_hours_urgency = os.getenv("SN_AFTER_HOURS_URGENCY")
after_hours_impact = os.getenv("SN_AFTER_HOURS_IMPACT")
business_hours_urgency = os.getenv("SN_BUSINESS_HOURS_URGENCY")
business_hours_impact = os.getenv("SN_BUSINESS_HOURS_IMPACT")


# Get the current time and day of the week
current_time = datetime.now().time()
current_day = datetime.now().weekday()

# Define business hours
business_hours_start = datetime.strptime(business_hours_start_time, "%H:%M:%S").time()
business_hours_end = datetime.strptime(business_hours_end_time, "%H:%M:%S").time()

# Set default values
urgency = after_hours_urgency  # Default value for after hours and weekends
impact = after_hours_urgency   # Default value for after hours and weekends

# Check if it's business hours
if business_hours_start <= current_time <= business_hours_end and current_day < 5:  # Monday to Friday
    urgency = business_hours_urgency
    impact = business_hours_impact


def check_cluster_node_health(ip_address):
    health_url = f"http://{ip_address}/status"

    try:
        response = requests.get(health_url, timeout=2)  # Set the timeout to 2 seconds
        response.raise_for_status()
        health_status = response.text.strip()
        logging.info(f"Node {ip_address}: {response.status_code} - {response.text.strip()}")
        return health_status
    except Timeout:
        health_status = "Unavailable: (Starting or Stopping)"
        logging.error(f"Node {ip_address}: Timeout")
    except requests.RequestException as e:
        health_status = f"Unavailable: (Starting or Stopping) {str(e)}"
        logging.error(f"Node {ip_address}: Error - {str(e)}")

    return health_status


def save_last_processed_event(last_processed_event, file_path):
    with open(file_path, 'w') as file:
        file.write(str(last_processed_event))


def load_last_processed_event(file_path):
    try:
        with open(file_path, 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        return None


# Process Core Dump
def process_core_dump(crashdump_file):
    crashdump_source_path = os.path.join(EI_jboss_path, crashdump_file)
    crashdump_log_file_name = os.path.splitext(crashdump_file)[0] + '.log'
    crashdump_log_source_path = os.path.join(log_dir, crashdump_log_file_name)
    destination_path = crashdump_logs_folder
    os.makedirs(destination_path, exist_ok=True)
    external_unique_id = str(uuid.uuid4())
    cluster_nodes = None

    try:
        # get timestamp of crash
        crash_timestamp_seconds = os.path.getmtime(crashdump_source_path)

        # Convert timestamp to local time
        dt_format = "%Y/%m/%d %H:%M:%S.%f"
        utc_dt = datetime.utcfromtimestamp(crash_timestamp_seconds)
        offset_minutes = int((datetime.utcnow() - datetime.now()).total_seconds() / 60)
        local_dt = utc_dt - timedelta(minutes=offset_minutes)
        crash_timestamp = local_dt.strftime(dt_format)

        # move crash dump out of bin folder to crash dump logs folder
        logging.info(f"Moving crash dump file from {crashdump_source_path} to {destination_path}")
        shutil.move(crashdump_source_path, destination_path)

        # copy matching crashdump logfile to crash dump logs folder
        logging.info(f"Copying crash dump log file from {crashdump_log_source_path} to {destination_path}")
        shutil.copy(crashdump_log_source_path, destination_path)

        # setup email variables
        subject = f"JBoss EAP Crashed on {os.environ['COMPUTERNAME']} at {crash_timestamp}"
        message = f"JBoss EAP Crashed\nTime: {crash_timestamp}\nCrash dump file: {crashdump_file}\nCluster FQDN: {EI_FQDN.upper()}\n"

        # Check cluster health
        cluster_nodes = lookup_available_nodes(EI_FQDN,EI_USER,EI_PASSWORD)
        # Check cluster nodes
        if cluster_nodes:
            message += f"\nCurrent Cluster Nodes: {cluster_nodes}"
            message = check_cluster_nodes(cluster_nodes, message)
        else:
            message += f"\nFailed to retrieve cluster nodes information."

        # Create ServiceNow incident and get the incident number
        incident_number, sys_id = create_service_now_incident(
            subject, message,'none',
            configuration_item, external_unique_id,
            urgency, impact, service_now_instance,service_now_table,service_now_api_user, service_now_api_password, assignment_group)

        # Attach the Log file to the ServiceNow incident
        if incident_number and sys_id:
            logging.info(f"Attaching crash dump log file to incident: {crashdump_log_source_path}")
            attach_file_to_ticket(sys_id, crashdump_log_source_path,service_now_instance,service_now_attachment_table,service_now_api_user, service_now_api_password)
            subject += f" Ticket: {incident_number}"

        # send email
        #logging.info(f"Email Body: {message}")
        send_email(smtp_recipients, subject, message, smtp_from,smtp_from_domain,smtp_server, smtp_port, meme_path=None)

        # Log information
        logging.info(f"Processed core dump: {crashdump_file}, Zip file: {crashdump_log_source_path} Ticket: {incident_number}")

    except Exception as e:
        logging.error(f"Error processing core dump: {e}")


# function to resolve and check cluster nodes
def check_cluster_nodes(cluster_nodes, message):
    cluster_nodes = re.findall(r'\b\d+\.\d+\.\d+\.\d+\b', cluster_nodes)
    new_message = message  # Create a new string based on the existing message

    for node in cluster_nodes:
        try:
            node_str = str(node)
            logging.info(f"Processing cluster node: {node_str}")

            ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', node_str)
            ip_address = ip_match.group() if ip_match else "Unknown"

            # Perform hostname lookup
            try:
                hostname, _, _ = socket.gethostbyaddr(ip_address)
                # Strip the domain part from the hostname
                if '.' in hostname:
                    hostname = hostname.split('.')[0]
            except (socket.herror, socket.gaierror):
                hostname = "Unknown"

            logging.info(f"Extracted IP address: {ip_address}, Hostname: {hostname}")

            health_status = check_cluster_node_health(ip_address)
            new_message += f"\n{node_str} ({hostname}): {health_status}"
        except Exception as e:
            logging.error(f"Error processing cluster node: {e}")
            logging.error(f"Node: {node_str}")
            logging.error(f"IP Address: {ip_address}")
            raise

    return new_message  # Return the new string


def quick_search_with_mmap(file_path):
    """Quickly search for JBoss EAP and specific events using memory-mapped files in reverse order and return the event type and line number."""
    with open(file_path, 'rb') as f:
        # Memory-map the file, size 0 means whole file
        with mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
            file_size = mm.size()
            current_pos = file_size  # Start from the end of the file
            line_number = 0
            found_event = None

            # Start reading the file backwards
            while current_pos > 0:
                # Move the pointer back and read byte by byte
                current_pos -= 1
                mm.seek(current_pos)
                byte = mm.read(1)

                # If we find a newline, process the line
                if byte == b'\n':
                    line = mm.readline().decode('utf-8', errors='ignore').strip()
                    line_number += 1

                    # First, check if "JBoss EAP" is in the line
                    if "JBoss EAP" in line:
                        # Check if the line contains "started" or "stopped"
                        if "started" in line:
                            logging.info(f"Found 'started' event with 'JBoss EAP' at line {line_number}")
                            found_event = (line_number, "started")
                        elif "stopped" in line:
                            logging.info(f"Found 'stopped' event with 'JBoss EAP' at line {line_number}")
                            found_event = (line_number, "stopped")

                    # Check separately for "Timeout reached after 60s"
                    elif "Timeout reached after 60s" in line:
                        logging.info(f"Found 'timeout' event at line {line_number}")
                        found_event = (line_number, "timeout")

                    # If an event is found, return the latest (i.e., closest to the end of the file)
                    if found_event:
                        return found_event

    return None, None  # Return None if no match is found


def extract_timestamp_from_line(timestamp_line):
    """Extract timestamp from a given log line."""
    time_start = timestamp_line.find('time="') + 6
    time_end = timestamp_line.find('"', time_start)
    if time_start != -1 and time_end != -1:
        return timestamp_line[time_start:time_end]
    else:
        logging.error("Failed to find timestamp in the line.")
        return None


def convert_to_local_time(utc_timestamp):
    """Convert a UTC timestamp to local time."""
    if not utc_timestamp:
        return None

    dt_format = "%Y/%m/%d %H:%M:%S.%f"
    try:
        utc_dt = datetime.strptime(utc_timestamp[:-6], dt_format)
        local_dt = utc_dt - timedelta(minutes=int((datetime.utcnow() - datetime.now()).total_seconds() / 60))
        return local_dt.strftime("%H:%M:%S %m/%d/%Y")
    except ValueError as ve:
        logging.error(f"Error parsing timestamp: {ve}")
        return None


def process_newest_two_log_files(log_files, last_processed_event):
    logging.info(f"Processing the newest two log files: {log_files[:2]}")
    newest_event = None
    newest_event_type = None
    local_timestamp = None

    # Loop over the two newest log files
    for log_file in log_files[:2]:
        logging.info(f"Performing quick event search in log file: {log_file}")

        # Use mmap to find the event type and match line number
        match_line_number, event_type = quick_search_with_mmap(log_file)
        if match_line_number is None:
            logging.info(f"No event found in {log_file}. Skipping further processing.")
            continue  # Skip to the next log file if no event exists

        logging.info(f"Event found at line {match_line_number} in {log_file}. Event type: {event_type}")

        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = list(f)  # Load all lines into memory

            # If the event is "started", process from the match line
            if event_type == "started":
                for i in range(len(lines)):
                    line = lines[i]
                    match = event_pattern.search(line)
                    if match:
                        newest_event = line.strip()
                        newest_event_type = match.group(2) or match.group(1)  # Check for "started" or "stopped"
                        logging.info(f"Found event: {newest_event}, type: {newest_event_type}")
                        # Get the previous line for timestamp
                        timestamp_line = lines[i - 1]
                        timestamp = extract_timestamp_from_line(timestamp_line)
                        local_timestamp = convert_to_local_time(timestamp)
                        break

            # If the event is "stopped" or "Timeout reached after 60s", process the file in reverse
            else:
                for i in reversed(range(len(lines))):
                    line = lines[i]
                    if "JBoss EAP" in line and ("stopped" in line or "Timeout reached after 60s" in line):
                        newest_event = line.strip()
                        logging.info(f"Processing '{event_type}' event: {newest_event}")

                        # Get the previous line for timestamp
                        timestamp_line = lines[i - 1]
                        timestamp = extract_timestamp_from_line(timestamp_line)
                        local_timestamp = convert_to_local_time(timestamp)
                        break

            # If a new event is found, process it and return
            if newest_event and newest_event != last_processed_event:
                logging.info(f"Processing new event: {newest_event}")
                cluster_nodes = lookup_available_nodes(EI_FQDN,EI_USER,EI_PASSWORD)

                subject = f"JBoss EAP {event_type.capitalize()} on {os.environ['COMPUTERNAME']} at {local_timestamp}"
                message = f"{newest_event}\nTime: {local_timestamp}\nCluster FQDN: {EI_FQDN.upper()}\n"
                #logging.info(f"Email Body: {message}")
                if cluster_nodes:
                    message += f"\nCurrent Cluster Nodes: {cluster_nodes}"
                    message = check_cluster_nodes(cluster_nodes, message)

                # Send alert email
                send_email(smtp_recipients, subject, message, smtp_from,smtp_from_domain,smtp_server, smtp_port, meme_path=None)

                # **Exit after processing the first found event**
                return newest_event
            logging.info("No new event found in the newest two log files.")
            return last_processed_event

        except FileNotFoundError as e:
            logging.error(f"Log file not found: {log_file}. Error: {e}")
        except Exception as e:
            logging.error(f"Error processing log file: {e}")

    # If no new event is found in both files, return the last processed event
    logging.info("No new event found in the newest two log files.")
    return last_processed_event


# Helper function to get sorted log files and return full paths
def get_sorted_log_files(log_dir):
    try:
        # Construct full paths and sort log files in reverse order
        log_files = sorted(
            [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.startswith('server-') and f.endswith('.log')],
            reverse=True
        )
        if log_files:
            logging.info(f"Found log files: {log_files}")
        return log_files
    except Exception as e:
        logging.error(f"Error retrieving log files: {e}")
        return []


def main():
    last_processed_event = load_last_processed_event(last_processed_event_file)

    try:
        logging.info('Processing log files...')

        # Get sorted log files
        log_files = get_sorted_log_files(log_dir)

        if log_files:
            # Ensure we are processing the newest two log files
            last_processed_event = process_newest_two_log_files(log_files, last_processed_event)

            # Save the last processed event to the file
            save_last_processed_event(last_processed_event, last_processed_event_file)

        # Process crash dump if any
        crashdumps = [os.path.join(EI_jboss_path, f) for f in os.listdir(EI_jboss_path) if f.endswith('.mdmp')]
        if crashdumps:
            crashdump_file = crashdumps[0]
            logging.info(f'Processing crashdump: {crashdump_file}')
            process_core_dump(crashdump_file)

    except Exception as e:
        logging.error(f"Error in main loop: {e}")


if __name__ == '__main__':
    main()