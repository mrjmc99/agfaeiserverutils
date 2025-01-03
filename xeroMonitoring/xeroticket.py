import base64
import json
import urllib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
import ast
import requests
import os
import configparser
import paramiko
import logging
import uuid
from time import sleep
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import concurrent.futures
import cx_Oracle
import urllib3
import textwrap

# ignore insecure warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Get the absolute path of the script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Set up logging
log_file_path = os.path.join(script_dir, "xero_ticket.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler()
    ]
)


# Construct the absolute path of the configuration file
config_file_path = os.path.join(script_dir, "xeroticket.ini")

# Load the configuration file
config = configparser.ConfigParser()
config.read(config_file_path)

# Xero API Variables
xero_user = config.get("Xero", "xero_user")
xero_password = config.get("Xero", "xero_password")
xero_domain = config.get("Xero", "xero_domain")
xero_query_constraints = config.get("Xero", "xero_query_constraints")
xero_nodes = config.get("Xero", "xero_nodes").split(',')
xero_restart_command = config.get("Xero", "xero_restart_command")
xero_haproxy_restart_command = config.get("Xero", "xero_haproxy_restart_command")
xero_disable_command = config.get("Xero", "xero_disable_command")
xero_wado_purge_command = config.get("Xero", "xero_wado_purge_command")
xero_server_user = config.get("Xero", "xero_server_user")
xero_server_private_key = config.get("Xero", "xero_server_private_key")
xero_get_ticket_timeout = int(config.get("Xero", "xero_get_ticket_timeout"))
xero_ticket_validation_timeout = int(config.get("Xero", "xero_ticket_validation_timeout"))
xero_retry_attempts = int(config.get("Xero", "xero_retry_attempts"))
xero_wado = ast.literal_eval(config.get("Xero", "xero_wado"))
validation_study_PatientID = config.get("Xero", "validation_study_PatientID")
validation_study_AccessionNumber = config.get("Xero", "validation_study_AccessionNumber")
xero_theme = config.get("Xero", "theme")
disabled_servers_file = os.path.join(script_dir, config.get("Xero", "disabled_servers_file"))
cluster_db_host = config.get("Xero", "cluster_db_host")
cluster_db_port = config.get("Xero", "cluster_db_port")
cluster_db_service_name = config.get("Xero", "cluster_db_service_name")
cluster_db_user = config.get("Xero", "cluster_db_user")
cluster_db_password = config.get("Xero", "cluster_db_password")


query_constraints = f"PatientID={validation_study_PatientID}, AccessionNumber={validation_study_AccessionNumber}"
display_vars = f"theme={xero_theme}, PatientID={validation_study_PatientID}, AccessionNumber={validation_study_AccessionNumber}"



# email variables
smtp_server = config.get("Email", "smtp_server")
smtp_port = int(config.get("Email", "smtp_port"))
smtp_username = config.get("Email", "smtp_username")
smtp_password = config.get("Email", "smtp_password")
smtp_from_domain = config.get("Email", "smtp_from_domain")
smtp_recipients_string = config.get("Email", "smtp_recipients")
smtp_recipients = smtp_recipients_string.split(",")

# meme variables
use_memes = config.getboolean("Meme", "use_memes")
successful_restart_meme_path = os.path.join(script_dir, 'memes', config.get("Meme", "successful_restart_meme"))
unsuccessful_restart_meme_path = os.path.join(script_dir, 'memes', config.get("Meme", "unsuccessful_restart_meme"))
temp_meme_path = os.path.join(script_dir, os.path.dirname('memes'), 'temp_meme.jpg')
font_path = os.path.join(script_dir, 'fonts', config.get("Meme", "font"))

# service now variables
service_now_instance = config.get("ServiceNow", "instance")
service_now_table = config.get("ServiceNow", "table")
service_now_api_user = config.get("ServiceNow", "api_user")
service_now_api_password = config.get("ServiceNow", "api_password")
ticket_type = config.get("ServiceNow", "ticket_type")
configuration_item = config.get("ServiceNow", "configuration_item")
assignment_group = config.get("ServiceNow", "assignment_group")
assignee = config.get("ServiceNow", "assignee")
business_hours_start_time = config.get("ServiceNow", "business_hours_start_time")
business_hours_end_time = config.get("ServiceNow", "business_hours_end_time")
after_hours_urgency = config.get("ServiceNow", "after_hours_urgency")
after_hours_impact = config.get("ServiceNow", "after_hours_impact")
business_hours_urgency = config.get("ServiceNow", "business_hours_urgency")
business_hours_impact = config.get("ServiceNow", "business_hours_impact")



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

local_time_str = datetime.now().time()

# Function to generate meme with better text size and positioning
def generate_meme(image_path, top_text, bottom_text, output_path):
    logging.info("Generating meme...")
    try:
        # Open the image
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)

        # Load the TrueType font
        max_width = img.width * 0.9  # Allow a 5% margin on either side
        max_font_size = img.height // 10  # Set a maximum font size based on image height

        font_size = max_font_size
        font = ImageFont.truetype(font_path, font_size)

        # Reduce font size until text fits within max_width
        def fit_text_to_width(text, font):
            while draw.textbbox((0, 0), text, font=font)[2] > max_width and font_size > 10:
                font = ImageFont.truetype(font_path, font.size - 2)
            return font

        # Adjust top text font
        font = fit_text_to_width(top_text, font)
        wrapped_top_text = textwrap.fill(top_text, width=40)

        # Draw top text
        top_y_position = 10
        draw.multiline_text(
            ((img.width - draw.textbbox((0, 0), wrapped_top_text, font=font)[2]) / 2, top_y_position),
            wrapped_top_text, fill="white", font=font, align="center"
        )

        # Adjust bottom text font
        font = fit_text_to_width(bottom_text, font)
        wrapped_bottom_text = textwrap.fill(bottom_text, width=40)

        # Draw bottom text at the bottom with a bit of padding
        bottom_y_position = img.height - draw.textbbox((0, 0), wrapped_bottom_text, font=font)[3] - 20
        draw.multiline_text(
            ((img.width - draw.textbbox((0, 0), wrapped_bottom_text, font=font)[2]) / 2, bottom_y_position),
            wrapped_bottom_text, fill="white", font=font, align="center"
        )

        # Save the meme
        img.save(output_path)
        logging.info(f"Meme saved at {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Failed to generate meme: {e}")
        raise



# disabled server management
class DisabledServerManager:
    @staticmethod
    def load_disabled_servers():
        try:
            with open(disabled_servers_file, 'r') as file:
                content = file.read().strip()
                return json.loads(content) if content else {}
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            # Create a new file or replace a blank file with an empty dictionary
            with open(disabled_servers_file, 'w') as file:
                json.dump({}, file)
            return {}

    @staticmethod
    def save_disabled_servers(servers):
        with open(disabled_servers_file, 'w') as file:
            json.dump(servers, file)

    @staticmethod
    def is_server_disabled(xero_server):
        servers = DisabledServerManager.load_disabled_servers()
        return xero_server in servers

    @staticmethod
    def save_disabled_server(xero_server, incident_number):
        servers = DisabledServerManager.load_disabled_servers()
        servers[xero_server] = incident_number
        DisabledServerManager.save_disabled_servers(servers)

    @staticmethod
    def remove_disabled_server(xero_server):
        servers = DisabledServerManager.load_disabled_servers()
        if xero_server in servers:
            incident = servers[xero_server]
            local_time_str = datetime.now().time()
            if incident == 'PREPARE':
                subject = f"Xero Ticketing/Image Display has been Restored on {xero_server} at {local_time_str}"
                body = f"Xero Ticketing/Image Display has been Restored on {xero_server} at {local_time_str}"
            else:
                subject = f"Xero Ticketing/Image Display has been Restored on {xero_server} at {local_time_str}"
                body = f"Xero Ticketing/Image Display has been Restored on {xero_server} at {local_time_str}\nPlease Close {incident}"
            if use_memes:
                generate_meme(successful_restart_meme_path, f"Xero Ticketing/Image Display has been Restored on {xero_server}",
                              "", temp_meme_path)
                send_email(smtp_recipients, subject, body, xero_server, temp_meme_path)
                os.remove(temp_meme_path)
            else:
                send_email(smtp_recipients, subject, body, xero_server)
            del servers[xero_server]
            DisabledServerManager.save_disabled_servers(servers)


# Function to encode an image as base64
def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
    return encoded_image


# Define a unified function to send emails, with optional meme attachment
def send_email(smtp_recipients, subject, body, node, meme_path=None):
    smtp_from = f"{node}@{smtp_from_domain}"
    msg = construct_email_message(smtp_from, smtp_recipients, subject, body, meme_path)

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.sendmail(smtp_from, smtp_recipients, msg.as_string())
        server.quit()
        logging.info(f"Email sent to {', '.join(smtp_recipients)}")
    except Exception as e:
        logging.error(f"Email sending failed to {', '.join(smtp_recipients)}: {e}")



# Helper function to construct email message with an embedded image
def construct_email_message(smtp_from, smtp_recipients, subject, body, meme_path=None):
    # Create a MIMEMultipart message to handle both HTML and image content
    msg = MIMEMultipart('related')
    msg["From"] = smtp_from
    msg["To"] = ", ".join(smtp_recipients)
    msg["Subject"] = subject

    # Create the HTML body, embedding the image with a CID
    body_html = body.replace("\n", "<br>")
    html_body = f"""
    <html>
        <body>
            <p>{body_html}</p>
            {"<img src='cid:meme_image' alt='Meme'>" if meme_path else ""}
        </body>
    </html>
    """
    # Attach the HTML body to the email
    msg.attach(MIMEText(html_body, 'html'))

    # Attach the image if the meme_path is provided
    if meme_path:
        with open(meme_path, 'rb') as img_file:
            meme_data = img_file.read()
            image_part = MIMEImage(meme_data)
            image_part.add_header('Content-ID', '<meme_image>')
            image_part.add_header('Content-Disposition', 'inline', filename='meme.jpg')
            msg.attach(image_part)

    return msg


def create_and_send_failure_incident(xero_server, failure_reason):
    local_time_str = datetime.now().time()
    subject = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} ({failure_reason})"
    body = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str}\nPlease investigate."
    incident_summary = subject
    external_unique_id = str(uuid.uuid4())
    incident_number = create_service_now_incident(
        incident_summary, body, configuration_item, external_unique_id, urgency, impact
    )
    if incident_number:
        subject += f" {incident_number}"
        DisabledServerManager.save_disabled_server(xero_server, incident_number)
    else:
        DisabledServerManager.save_disabled_server(xero_server, "Ticket Creation Failed")

    send_email(smtp_recipients, subject, body, xero_server)


def create_service_now_incident(summary, description, configuration_item, external_unique_id, urgency, impact):
    incident_api_url = f"https://{service_now_instance}/api/now/table/{service_now_table}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "u_short_description": summary,
        "u_description": description,
        "u_affected_user_id": "",
        "u_configuration_item": configuration_item,
        "u_external_unique_id": external_unique_id,
        "u_urgency": urgency,
        "u_impact": impact,
        "u_type": ticket_type,
        "u_assignment_group": assignment_group,
    }

    try:
        # logging.info("Incident Creation Payload:", payload)  # Print payload for debugging
        response = requests.post(
            incident_api_url,
            headers=headers,
            auth=(service_now_api_user, service_now_api_password),
            json=payload,
        )

        # logging.info("Incident Creation Response Status Code:", response.status_code)  # Print status code for debugging
        # logging.info("Incident Creation Response Content:", response.text)  # Print response content for debugging

        if response.status_code == 201:
            incident_number = response.json().get("result", {}).get("u_task_string")
            sys_id = response.json().get('result', {}).get('u_task', {}).get('value')
            logging.info(f"ServiceNow incident created successfully: {incident_number}")
            return incident_number
        else:
            logging.info(f"Failed to create ServiceNow incident. Response: {response.text}")

    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred while creating ServiceNow incident: {e}")

    return None


def get_xero_ticket(xero_server, retry_amount=xero_retry_attempts):
    api_url = f"https://{xero_server}/encodedTicket"

    # URL encode the query constraints and display vars
    query_constraints_encoded = urllib.parse.quote(query_constraints)
    display_vars_encoded = urllib.parse.quote(display_vars)
    # logging.info(query_constraints_encoded)
    # logging.info(display_vars_encoded)
    payload = {
        "user": xero_user,
        "password": xero_password,
        "domain": xero_domain,
        "queryConstraints": query_constraints_encoded,
        # "initialDisplay": display_vars_encoded,
        "ticketDuration": "300",
        "uriEncodedTicket": "true",
        "ticketUser": "TICKET_TESTING_USER",
        "ticketRoles": "EprUser",
    }

    headers = {}

    for attempt in range(retry_amount):
        try:
            logging.info(f"Testing Ticket Creation for {xero_server}, Attempt {attempt + 1}")
            response = requests.post(api_url, headers=headers, data=payload, verify=False,
                                     timeout=xero_get_ticket_timeout)
            # logging.info(f"{xero_server} Ticket Creation Response Status Code: {response.status_code}")  # Print status code for debugging
            if response.status_code == 200:
                logging.info(f"{xero_server} created a ticket successfully")
                # logging.info(response.text)
                return response.text
            else:
                logging.info(f"{xero_server} Ticket Creation Failure, Status Code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logging.error(f"An error occurred while attempting to create xero tickets on {xero_server}: {e}")

        # Wait before retrying
        sleep(2)

    logging.error(f"Failed to create xero ticket after {retry_amount} attempts")
    return None


def verify_ticket(xero_server, xero_ticket, retry_amount=xero_retry_attempts):
    verification_url = f"https://{xero_server}/?PatientID={validation_study_PatientID}&AccessionNumber={validation_study_AccessionNumber}&theme={xero_theme}&ticket={xero_ticket}"

    for attempt in range(retry_amount):
        try:
            logging.info(f"Verifying Ticket for {xero_server}, Attempt {attempt + 1}")
            response = requests.get(verification_url, verify=False, timeout=xero_ticket_validation_timeout)
            # logging.info(f"{xero_server} Verification URL Response Status Code: {response.status_code}")
            # logging.info(f"Verification URL Response Content: {response.text}")

            if response.status_code == 200:
                logging.info(f"{xero_server} Ticket verification successful")
                return True
            else:
                logging.info(f"{xero_server} Ticket verification failed, Status Code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logging.error(f"An error occurred while attempting to verify the ticket: {e}")

        # Wait before retrying
        sleep(2)

    logging.error(f"Failed to verify xero ticket after {retry_amount} attempts")
    return False


def get_and_verify_ticket(xero_server):
    xero_ticket = get_xero_ticket(xero_server)
    if xero_ticket:
        if verify_ticket(xero_server, xero_ticket):
            if DisabledServerManager.is_server_disabled(xero_server):
                DisabledServerManager.remove_disabled_server(xero_server)
            return True
        return False
    return False


#  check for upgrade pending/inprogress
def check_for_upgrade(xero_server):
    # Oracle database connection details
    dsn = cx_Oracle.makedsn(cluster_db_host, cluster_db_port, service_name=cluster_db_service_name)
    connection = cx_Oracle.connect(user=cluster_db_user, password=cluster_db_password, dsn=dsn)

    query = """
    select t.installstage "Installation Stage", inode.id "Cluster node"
    from installer_node inode,
    xmltable('/installStatus' 
        passing xmltype(inode.status) 
        columns 
            installstage varchar2(64) path 'stage',
            uninstalled varchar2(64) path 'uninstall'
        ) t
    where upper(inode.id) like upper(:xero_server)
    and uninstalled = 'false'
    and installstage = 'PREPARE'
    """

    try:
        cursor = connection.cursor()
        cursor.execute(query, xero_server=f"{xero_server}%")
        result = cursor.fetchone()
        logging.info(f"upgrade check for {xero_server} result is:{result}")
        return result is not None

    except cx_Oracle.DatabaseError as e:
        # Specifically catch Oracle-related errors
        logging.error(f"Database error occurred: {e}; continuing with restarts...")
        return False

    except Exception as e:
        # Catch ANY other exception
        logging.error(f"An unexpected error occurred: {e}")
        return False
    finally:
        cursor.close()
        connection.close()


def restart_xero_services(xero_server):
    try:
        commands = [
            (xero_haproxy_restart_command, "HAProxy"),
            (xero_restart_command, "JBoss")
        ]
        for command, service_name in commands:
            logging.info(f"Attempting to restart {service_name} on {xero_server}")
            result = execute_remote_command(
                xero_server, xero_server_user, xero_server_private_key, command
            )
            logging.info(f"{service_name} restarted successfully on {xero_server}: {result}")
    except Exception as e:
        logging.error(f"Error restarting services on Xero server ({xero_server}): {e}")
        create_and_send_failure_incident(xero_server, "Unable to connect to server")
        return None


def disable_xero_server(xero_server):
    try:
        logging.info(f"attempting to disable xero services on {xero_server}")
        result = execute_remote_command(
            xero_server,
            xero_server_user,
            xero_server_private_key,
            xero_disable_command,
        )
    except Exception as e:
        logging.error(f"Error Disabling Xero server ({xero_server}): {e}")
        subject = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server) (Ticket Creation Failure))"
        body = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server)/nPlease investigate"
        incident_summary = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server)"
        incident_description = body
        external_unique_id = str(uuid.uuid4())
        incident_number = create_service_now_incident(
            incident_summary, incident_description,
            configuration_item, external_unique_id,
            urgency, impact
        )
        if incident_number:
            logging.info(incident_number)
            subject = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server) {incident_number}"
            DisabledServerManager.save_disabled_server(xero_server, incident_number)
        else:
            DisabledServerManager.save_disabled_server(xero_server, "Ticket Creation Failed")
        if use_memes:
            generate_meme(unsuccessful_restart_meme_path, "ONE DOES NOT SIMPLY",f"DISABLE XERO SERVICES ON {xero_server}", temp_meme_path)
            send_email(smtp_recipients, subject, body, xero_server, temp_meme_path)
            os.remove(temp_meme_path)
        else:
            send_email(smtp_recipients, subject, body, xero_server)
    else:
        logging.info(f"Xero server Disabling successfully: {result}")
        subject = f"Xero Ticketing/Image Display has been Disabled on {xero_server} at {local_time_str}"
        body = f"Xero Ticketing/Image Display has been Disabled on {xero_server} at {local_time_str}\nTo enable the server run the following command on the xero server: sudo agility-haproxy restart"
        #body = f"Xero Ticketing/Image Display has been Disabled on {xero_server} at {local_time_str}\nTo manually purge cache run the following command: sudo /bin/nice -n +15 /bin/find /wado2cache* -mmin +240 -delete \nTo enable the server run the following command on the xero server: sudo agility-haproxy start"
        incident_summary = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Server Disabled)"
        incident_description = body
        external_unique_id = str(uuid.uuid4())
        incident_number = create_service_now_incident(
            incident_summary, incident_description,
            configuration_item, external_unique_id,
            urgency, impact
        )
        if incident_number:
            logging.info(incident_number)
            subject = f"Xero Ticketing/Image Display has been Disabled on {xero_server} at {local_time_str} {incident_number}"
            DisabledServerManager.save_disabled_server(xero_server,incident_number)
        else:
            DisabledServerManager.save_disabled_server(xero_server, "Ticket Creation Failed")
        if use_memes:
            generate_meme(unsuccessful_restart_meme_path, "ONE DOES NOT SIMPLY",f"RESTART XERO SERVICES ON {xero_server}", temp_meme_path)
            send_email(smtp_recipients, subject, body, xero_server, temp_meme_path)
            os.remove(temp_meme_path)
        else:
            send_email(smtp_recipients, subject, body, xero_server)
    return None  # Return the result or another suitable value


def execute_remote_command(hostname, username, private_key_path, command):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(hostname, username=username, key_filename=private_key_path)
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()

        result = {'output': output, 'error': error}
        ssh.close()
        return result
    except Exception as e:
        logging.error(f"Error executing remote command: {e}")
        return None



def notify_failed_server_pending_upgrade(xero_server):
    subject = f"Xero Ticketing/Image Display Failing on {xero_server} at {local_time_str} (Server in PREPARE Status)"
    body = f"Xero Ticketing/Image Display Failing on {xero_server} at {local_time_str} (Server in PREPARE Status)\n The server will has been placed on the disabled servers lists, and will be removed automacailly after the upgrade is complete and ticketing is validated."
    send_email(smtp_recipients, subject, body, xero_server)
    DisabledServerManager.save_disabled_server(xero_server, "PREPARE")
    return

def process_node(node):
    if get_and_verify_ticket(node):
        return
    logging.info(f"Ticket Creation failed for {node}")
    if DisabledServerManager.is_server_disabled(node):
        logging.info(f"Skipping {node} - Server is already disabled.")
        return

    server_in_prepare_status = check_for_upgrade(node)
    if server_in_prepare_status:
        logging.info(f"Skipping {node} - Server is in a PREPARE Status")
        notify_failed_server_pending_upgrade(node)
        return

    restart_xero_services(node)
    sleep(10)  # Wait and retry
    logging.info("Restart Completed, waiting 10 seconds to retest")
    if not get_and_verify_ticket(node):
        logging.info(f"Ticket Creation failed for {node} Disabling Server")
        disable_xero_server(node)
    else:
        subject = f"Xero Ticketing/Image Display has been Restored on {node} at {local_time_str}"
        body = f"Xero Ticketing/Image Display has been Restored on {node} at {local_time_str}"
        if use_memes:
            generate_meme(successful_restart_meme_path,
                          f"Xero Ticketing/Image Display has been Restored on {node}",
                          "", temp_meme_path)
            send_email(smtp_recipients, subject, body, node, temp_meme_path)
            os.remove(temp_meme_path)
        else:
            send_email(smtp_recipients, subject, body, node)




def main():
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(process_node, xero_nodes)
    logging.info("All tasks completed. Shutting down.")

def meme_testing():
    xero_server = "TESTSERVER"
    generate_meme(successful_restart_meme_path, f"Xero Ticketing/Image Display has been Restored on {xero_server}","", temp_meme_path)
    #generate_meme(unsuccessful_restart_meme_path, "ONE DOES NOT SIMPLY", f"RESTART XERO SERVICES ON {xero_server}", temp_meme_path)
    subject = f"Xero Ticketing/Image Display has been Restored on {xero_server} at {local_time_str}"
    body = f"Xero Ticketing/Image Display has been Restored on {xero_server} at {local_time_str}"
    send_email(smtp_recipients, subject, body, xero_server, temp_meme_path)
    #os.remove(temp_meme_path)

if __name__ == '__main__':
    main()
    #meme_testing()